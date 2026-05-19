"""Синхронизация справочника пользователей портала Bitrix24.

Тянем `user.get` пакетами и заливаем в таблицу `portal_users`. Используется
в дашборде для отображения имени/аватара по `Conversation.assigned_user_id`
и `Message.sender_external_id` без обращения к Bitrix24 на каждый рендер.

Стратегия:
- На каждом проходе поллера дёргается `sync_portal_users_if_stale` —
  если кэш не обновлялся > `users_sync_interval_sec`, делаем полный
  пересбор операторов. Без флага — пропускаем (дешёвая проверка).
- API `user.get` поддерживает пагинацию через `start` (по 50 записей).
- Сохраняем только активных + тех, кого видели в диалогах. На MVP —
  всех, кого вернёт `user.get` без фильтра.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, PortalLine, PortalUser
from app.integrations.bitrix24.client import BitrixAPIError, BitrixClient

logger = logging.getLogger(__name__)


def _full_name(user: dict[str, Any]) -> str | None:
    parts = [
        user.get("NAME") or user.get("name"),
        user.get("LAST_NAME") or user.get("last_name"),
    ]
    full = " ".join(p for p in parts if p).strip()
    return full or user.get("EMAIL") or user.get("email") or None


def _coerce_str(value: Any) -> str | None:
    if value in (None, "", 0, "0"):
        return None
    return str(value)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("y", "yes", "true", "1")
    return bool(value)


async def sync_portal_users(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
    *,
    page_size: int = 50,
    max_pages: int = 40,
) -> int:
    """Полная синхронизация `portal_users` для одной интеграции.

    Возвращает кол-во upsert'нутых записей. Логирует и не падает на API-ошибках.
    """
    upserted = 0
    start = 0
    for _ in range(max_pages):
        try:
            page = await client.call(
                "user.get",
                {"start": start, "FILTER": {"USER_TYPE": "employee"}},
            )
        except BitrixAPIError as exc:
            logger.warning(
                "user.get failed integration=%s start=%s: %s",
                integration.id,
                start,
                exc,
            )
            break

        # Bitrix отдаёт массив; пагинация — по start.
        users = page if isinstance(page, list) else []
        if not users:
            break

        ext_ids = [_coerce_str(u.get("ID") or u.get("id")) for u in users]
        ext_ids = [x for x in ext_ids if x]
        existing_rows = await session.execute(
            select(PortalUser).where(
                PortalUser.integration_id == integration.id,
                PortalUser.external_id.in_(ext_ids),
            )
        )
        existing = {p.external_id: p for p in existing_rows.scalars().all()}

        now = datetime.now(UTC)
        for u in users:
            if not isinstance(u, dict):
                continue
            ext_id = _coerce_str(u.get("ID") or u.get("id"))
            if not ext_id:
                continue
            full_name = _full_name(u)
            email = u.get("EMAIL") or u.get("email")
            position = u.get("WORK_POSITION") or u.get("work_position")
            avatar = u.get("PERSONAL_PHOTO") or u.get("personal_photo")
            active = _bool(u.get("ACTIVE", True))

            row = existing.get(ext_id)
            if row:
                row.full_name = full_name
                row.email = email
                row.work_position = position
                row.avatar_url = avatar
                row.is_active = active
                row.last_synced_at = now
            else:
                session.add(
                    PortalUser(
                        id=f"pu_{secrets.token_urlsafe(8).lower()}",
                        integration_id=integration.id,
                        external_id=ext_id,
                        full_name=full_name,
                        email=email,
                        work_position=position,
                        avatar_url=avatar,
                        is_active=active,
                        last_synced_at=now,
                    )
                )
            upserted += 1
        await session.flush()

        if len(users) < page_size:
            break
        start += page_size

    await session.commit()
    logger.info(
        "user.get sync: integration=%s upserted=%d",
        integration.id,
        upserted,
    )
    return upserted


async def sync_portal_lines(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
) -> int:
    """Полная синхронизация `portal_lines` — справочник открытых линий.

    Bitrix24 отдаёт всё одним вызовом без пагинации (линий обычно мало,
    единицы-десятки). Bitrix-метод: `imopenlines.config.list.get`.
    """
    try:
        rows = await client.call("imopenlines.config.list.get", {})
    except BitrixAPIError as exc:
        logger.warning(
            "imopenlines.config.list.get failed integration=%s: %s",
            integration.id,
            exc,
        )
        return 0

    if not isinstance(rows, list):
        return 0

    ext_ids: list[str] = []
    parsed: list[tuple[str, str | None, bool]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ext_id = _coerce_str(row.get("ID") or row.get("id"))
        if not ext_id:
            continue
        name = row.get("LINE_NAME") or row.get("line_name") or row.get("NAME") or None
        # ACTIVE может быть "Y"/"N"; по умолчанию считаем активной.
        active = _bool(row.get("ACTIVE", "Y"))
        ext_ids.append(ext_id)
        parsed.append((ext_id, name, active))

    if not ext_ids:
        return 0

    existing_rows = await session.execute(
        select(PortalLine).where(
            PortalLine.integration_id == integration.id,
            PortalLine.external_id.in_(ext_ids),
        )
    )
    existing = {p.external_id: p for p in existing_rows.scalars().all()}

    now = datetime.now(UTC)
    for ext_id, name, active in parsed:
        row = existing.get(ext_id)
        if row:
            row.name = name
            row.is_active = active
            row.last_synced_at = now
        else:
            session.add(
                PortalLine(
                    id=f"pl_{secrets.token_urlsafe(8).lower()}",
                    integration_id=integration.id,
                    external_id=ext_id,
                    name=name,
                    is_active=active,
                    last_synced_at=now,
                )
            )
    await session.flush()
    await session.commit()
    logger.info(
        "imopenlines.config.list.get sync: integration=%s lines=%d",
        integration.id,
        len(parsed),
    )
    return len(parsed)


async def sync_portal_users_if_stale(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
    *,
    stale_after: timedelta = timedelta(hours=24),
) -> bool:
    """Запускает синхронизацию операторов И линий, если давно не было."""
    last = (
        await session.execute(
            select(PortalUser.last_synced_at)
            .where(PortalUser.integration_id == integration.id)
            .order_by(PortalUser.last_synced_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last and (datetime.now(UTC) - last) < stale_after:
        return False
    await sync_portal_users(client, session, integration)
    await sync_portal_lines(client, session, integration)
    return True
