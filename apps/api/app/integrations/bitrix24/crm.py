"""CRM-обогащение импорта Open Channels.

Что делает:
1. Извлекает ссылки на Lead/Deal/Contact/Company из блока `session` ответа
   `imopenlines.session.history.get` — поддерживает разные форматы Bitrix24.
2. Один раз на импорт подтягивает справочник стадий (`crm.status.list`) для
   Lead и Deal в кэш `portal_stages`, чтобы перевести `STAGE_ID` сущности
   в семантику (won/lost/in_progress).
3. Батчем дотягивает Deal/Lead через `crm.deal.list` / `crm.lead.list`
   (по ID[]): TITLE, STAGE_ID, OPPORTUNITY, CURRENCY_ID, ASSIGNED_BY_ID,
   CLOSEDATE. Contact/Company — только id и попытка title через `crm.contact.list`
   / `crm.company.list`.

Документация:
  https://apidocs.bitrix24.ru/api-reference/crm/deals/crm-deal-list.html
  https://apidocs.bitrix24.ru/api-reference/crm/status/crm-status-list.html
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Conversation,
    ConversationCrmLink,
    CrmEntity,
    CrmEntityKind,
    CrmStageSemantics,
    Integration,
    PortalStage,
)
from app.integrations.bitrix24.client import BitrixAPIError, BitrixClient

logger = logging.getLogger(__name__)


# Разные представления типа сущности, встречающиеся в session/CRM-объектах B24.
_KIND_ALIASES: dict[str, CrmEntityKind] = {
    "LEAD": CrmEntityKind.lead,
    "L": CrmEntityKind.lead,
    "1": CrmEntityKind.lead,
    "DEAL": CrmEntityKind.deal,
    "D": CrmEntityKind.deal,
    "2": CrmEntityKind.deal,
    "CONTACT": CrmEntityKind.contact,
    "C": CrmEntityKind.contact,
    "3": CrmEntityKind.contact,
    "COMPANY": CrmEntityKind.company,
    "CO": CrmEntityKind.company,
    "4": CrmEntityKind.company,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(8).lower()}"


def _normalize_kind(raw: Any) -> CrmEntityKind | None:
    if raw is None:
        return None
    key = str(raw).strip().upper()
    return _KIND_ALIASES.get(key)


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def extract_crm_refs_from_session(
    history: dict[str, Any],
) -> list[tuple[CrmEntityKind, str]]:
    """Достаёт привязки из `session` блока ответа `imopenlines.session.history.get`.

    Возвращает список уникальных (kind, external_id). Bitrix отдаёт CRM-привязки
    в разных формах в зависимости от версии: одиночные поля `CRM_ENTITY_TYPE`/
    `CRM_ENTITY_ID`, либо словарь `crm`/`CRM` вида `{"LEAD": ["123"], ...}`,
    либо массив `crm_entities` (`{ENTITY_TYPE, ENTITY_ID}`).
    """
    out: list[tuple[CrmEntityKind, str]] = []
    seen: set[tuple[CrmEntityKind, str]] = set()

    def _add(kind: CrmEntityKind | None, ext_id: Any) -> None:
        if kind is None or ext_id in (None, "", 0, "0"):
            return
        key = (kind, str(ext_id))
        if key in seen:
            return
        seen.add(key)
        out.append(key)

    session = history.get("session")
    if not isinstance(session, dict):
        return out

    # Форма 1: одиночные поля.
    single_kind = _normalize_kind(
        session.get("CRM_ENTITY_TYPE") or session.get("crm_entity_type")
    )
    single_id = session.get("CRM_ENTITY_ID") or session.get("crm_entity_id")
    _add(single_kind, single_id)

    # Форма 2: массив объектов.
    entities = session.get("crm_entities") or session.get("CRM_ENTITIES")
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            _add(
                _normalize_kind(ent.get("ENTITY_TYPE") or ent.get("entity_type")),
                ent.get("ENTITY_ID") or ent.get("entity_id"),
            )

    # Форма 3: словарь {LEAD: [...], DEAL: [...]}.
    crm = session.get("crm") or session.get("CRM")
    if isinstance(crm, dict):
        for raw_kind, ids in crm.items():
            kind = _normalize_kind(raw_kind)
            if kind is None:
                continue
            if isinstance(ids, list):
                for x in ids:
                    _add(kind, x)
            else:
                _add(kind, ids)

    return out


async def upsert_link(
    session: AsyncSession,
    integration: Integration,
    conv: Conversation,
    *,
    kind: CrmEntityKind,
    external_id: str,
) -> CrmEntity:
    """Идемпотентно создаёт CrmEntity-заглушку и связь с диалогом."""
    existing = (
        await session.execute(
            select(CrmEntity).where(
                CrmEntity.integration_id == integration.id,
                CrmEntity.kind == kind,
                CrmEntity.external_id == external_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = CrmEntity(
            id=_new_id("crm"),
            integration_id=integration.id,
            kind=kind,
            external_id=external_id,
            status_semantics=CrmStageSemantics.in_progress,
        )
        session.add(existing)
        await session.flush()

    link_exists = (
        await session.execute(
            select(ConversationCrmLink).where(
                ConversationCrmLink.conversation_id == conv.id,
                ConversationCrmLink.crm_entity_id == existing.id,
            )
        )
    ).scalar_one_or_none()
    if link_exists is None:
        session.add(
            ConversationCrmLink(
                conversation_id=conv.id,
                crm_entity_id=existing.id,
            )
        )
        await session.flush()
    return existing


_SEMANTICS_MAP = {
    "S": CrmStageSemantics.won,
    "F": CrmStageSemantics.lost,
}

# Какие ENTITY_ID отправлять в crm.status.list для нужных kind.
_STATUS_ENTITY_ID = {
    CrmEntityKind.deal: "DEAL_STAGE",
    CrmEntityKind.lead: "STATUS",  # лиды в Bitrix24 в crm.status.list: ENTITY_ID=STATUS
}


async def sync_stages_cache(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
    kinds: set[CrmEntityKind],
) -> dict[tuple[CrmEntityKind, str], CrmStageSemantics]:
    """Подтягивает справочник стадий для нужных kind. Возвращает индекс
    `(kind, external_id) → semantics` (включая уже закешированные стадии).
    Категории сделок (C{n}:STAGE) подтягиваются вместе с обычными — Bitrix
    отдаёт их в той же crm.status.list при `ENTITY_ID=DEAL_STAGE`.
    """
    index: dict[tuple[CrmEntityKind, str], CrmStageSemantics] = {}
    relevant = {k for k in kinds if k in _STATUS_ENTITY_ID}
    if not relevant:
        return index

    now = datetime.now(UTC)
    for kind in relevant:
        entity_id = _STATUS_ENTITY_ID[kind]
        try:
            rows = await client.call(
                "crm.status.list",
                {"filter": {"ENTITY_ID": entity_id}, "order": {"SORT": "ASC"}},
            )
        except BitrixAPIError as exc:
            logger.warning(
                "crm.status.list failed entity_id=%s: %s", entity_id, exc
            )
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            stage_id = str(row.get("STATUS_ID") or row.get("status_id") or "")
            if not stage_id:
                continue
            semantics_raw = row.get("SEMANTICS") or row.get("semantics")
            semantics = _SEMANTICS_MAP.get(
                str(semantics_raw).upper() if semantics_raw else "",
                CrmStageSemantics.in_progress,
            )
            name = row.get("NAME") or row.get("name")
            sort_raw = row.get("SORT") or row.get("sort")
            try:
                sort_val = int(sort_raw) if sort_raw is not None else None
            except (TypeError, ValueError):
                sort_val = None

            existing = (
                await session.execute(
                    select(PortalStage).where(
                        PortalStage.integration_id == integration.id,
                        PortalStage.entity_kind == kind,
                        PortalStage.external_id == stage_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    PortalStage(
                        id=_new_id("stage"),
                        integration_id=integration.id,
                        entity_kind=kind,
                        external_id=stage_id,
                        name=name,
                        semantics=semantics,
                        sort=sort_val,
                        last_synced_at=now,
                    )
                )
            else:
                existing.name = name or existing.name
                existing.semantics = semantics
                existing.sort = sort_val if sort_val is not None else existing.sort
                existing.last_synced_at = now
            index[(kind, stage_id)] = semantics
        await session.flush()
    return index


def _to_decimal(value: Any) -> float | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_LIST_METHODS = {
    CrmEntityKind.deal: (
        "crm.deal.list",
        ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "CURRENCY_ID",
         "ASSIGNED_BY_ID", "CLOSEDATE", "CLOSED"],
    ),
    CrmEntityKind.lead: (
        "crm.lead.list",
        ["ID", "TITLE", "STATUS_ID", "OPPORTUNITY", "CURRENCY_ID",
         "ASSIGNED_BY_ID", "DATE_CLOSED"],
    ),
    CrmEntityKind.contact: (
        "crm.contact.list",
        ["ID", "NAME", "LAST_NAME", "ASSIGNED_BY_ID"],
    ),
    CrmEntityKind.company: (
        "crm.company.list",
        ["ID", "TITLE", "ASSIGNED_BY_ID"],
    ),
}


async def refresh_known_crm_entities(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
) -> int:
    """Дельта-синхронизация CRM-сущностей без активности диалогов.

    Зачем: статус сделки в Bitrix24 меняется в CRM, а не в чате. Если у
    диалога нет новых сообщений, импортёр Open Channels не появится в
    `im.recent.get` → мы не дёрнем `crm.deal.list` и не узнаем, что
    сделка стала won/lost. Эта функция вызывается отдельным cron-джобом
    воркера и обновляет ВСЕ известные нам сущности интеграции.

    Возвращает число обновлённых записей. Если сущностей нет — 0.
    """
    rows = (
        await session.execute(
            select(CrmEntity).where(CrmEntity.integration_id == integration.id)
        )
    ).scalars().all()
    if not rows:
        return 0

    kinds = {e.kind for e in rows}
    stage_index = await sync_stages_cache(client, session, integration, kinds)
    await enrich_entities(client, session, integration, rows, stage_index)
    await session.commit()
    return len(rows)


async def enrich_entities(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
    entities: list[CrmEntity],
    stage_index: dict[tuple[CrmEntityKind, str], CrmStageSemantics],
) -> None:
    """Дотягивает детали сущностей и выставляет status_semantics по справочнику.

    Запросы идут по 50 ID за раз (`crm.deal.list?filter[@ID]`). Поля типа
    OPPORTUNITY/CURRENCY пишутся в `CrmEntity.amount`/`currency`,
    `STAGE_ID`/`STATUS_ID` → `stage_external_id`, далее семантика берётся
    из `stage_index` (если нет — оставляем in_progress).
    """
    by_kind: dict[CrmEntityKind, list[CrmEntity]] = {}
    for ent in entities:
        by_kind.setdefault(ent.kind, []).append(ent)

    for kind, group in by_kind.items():
        if kind not in _LIST_METHODS:
            continue
        method, fields = _LIST_METHODS[kind]
        ids = [e.external_id for e in group]
        index = {e.external_id: e for e in group}

        # Bitrix фильтр @ID = "IN" — поддерживается, но возвращает до 50.
        for chunk_start in range(0, len(ids), 50):
            chunk = ids[chunk_start : chunk_start + 50]
            try:
                rows = await client.call(
                    method,
                    {
                        "filter": {"@ID": chunk},
                        "select": fields,
                    },
                )
            except BitrixAPIError as exc:
                logger.warning("%s failed: %s", method, exc)
                continue
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                ent_id = str(row.get("ID") or row.get("id") or "")
                ent = index.get(ent_id)
                if ent is None:
                    continue

                if kind == CrmEntityKind.deal:
                    ent.title = row.get("TITLE") or ent.title
                    stage = str(row.get("STAGE_ID") or "") or None
                    ent.stage_external_id = stage or ent.stage_external_id
                    if stage:
                        ent.status_semantics = stage_index.get(
                            (CrmEntityKind.deal, stage),
                            ent.status_semantics,
                        )
                    ent.amount = _to_decimal(row.get("OPPORTUNITY"))
                    ent.currency = row.get("CURRENCY_ID") or ent.currency
                    ent.assigned_user_id = (
                        str(row.get("ASSIGNED_BY_ID"))
                        if row.get("ASSIGNED_BY_ID")
                        else ent.assigned_user_id
                    )
                    if row.get("CLOSED") in ("Y", True, "true", 1, "1"):
                        ent.closed_at = (
                            _parse_iso(row.get("CLOSEDATE")) or ent.closed_at
                        )
                elif kind == CrmEntityKind.lead:
                    ent.title = row.get("TITLE") or ent.title
                    stage = str(row.get("STATUS_ID") or "") or None
                    ent.stage_external_id = stage or ent.stage_external_id
                    if stage:
                        ent.status_semantics = stage_index.get(
                            (CrmEntityKind.lead, stage),
                            ent.status_semantics,
                        )
                    ent.amount = _to_decimal(row.get("OPPORTUNITY"))
                    ent.currency = row.get("CURRENCY_ID") or ent.currency
                    ent.assigned_user_id = (
                        str(row.get("ASSIGNED_BY_ID"))
                        if row.get("ASSIGNED_BY_ID")
                        else ent.assigned_user_id
                    )
                    ent.closed_at = (
                        _parse_iso(row.get("DATE_CLOSED")) or ent.closed_at
                    )
                elif kind == CrmEntityKind.contact:
                    name = " ".join(
                        s for s in (row.get("NAME"), row.get("LAST_NAME")) if s
                    ).strip()
                    if name:
                        ent.title = name
                elif kind == CrmEntityKind.company:
                    ent.title = row.get("TITLE") or ent.title

        await session.flush()
