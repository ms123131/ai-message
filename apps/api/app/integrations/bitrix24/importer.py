"""
Исторический импорт диалогов Open Channels из Bitrix24.

MVP-стратегия (фаза 3.3):
1. `im.recent.get` с `ONLY_OPENLINES=Y` — список чатов, видимых пользователю
   токена/вебхука. Фильтруем по `date_last_activity >= cutoff`.
2. На каждый чат — `imopenlines.session.history.get` с `CHAT_ID`. Метод вернёт
   последнюю сессию: chat-meta, сообщения, участников.
3. Upsert: `Conversation.external_id = chat_id`, `Message.external_id = msg_id`.
   Дедуп через уникальные индексы (`uq_conversations_integration_external`,
   `uq_messages_conversation_external`) + предварительные SELECT'ы.

Что НЕ делает MVP:
- Не подтягивает все закрытые сессии чата — только последнюю, видимую через
  history.get(CHAT_ID). Полная история всех сессий потребует пагинации
  session-id и оставлена на будущее.
- Не качает вложения с Bitrix Disk — сохраняем только метаданные в `attachments`.

Документация:
  https://apidocs.bitrix24.ru/api-reference/chats/im-recent-get.html
  https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/sessions/imopenlines-session-history-get.html
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    CrmEntity,
    ImportJob,
    ImportJobStatus,
    Integration,
    Message,
    SenderType,
)
from app.integrations.bitrix24.client import BitrixAPIError, BitrixClient
from app.integrations.bitrix24.crm import (
    enrich_entities,
    extract_crm_refs_from_session,
    sync_stages_cache,
    upsert_link,
)
from app.integrations.bitrix24.events import map_connector_to_channel

logger = logging.getLogger(__name__)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(8).lower()}"


def _parse_iso(value: Any) -> datetime | None:
    """Bitrix24 отдаёт даты в ATOM (ISO-8601), напр. 2026-02-26T00:01:25+03:00."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _line_id_from_entity_id(entity_id: str | None) -> str | None:
    """Достаёт ID открытой линии (CONFIG_ID) из `chat.entityId`.

    Формат в Bitrix24:
      `imol|<connector>|<line>|<user>`     — внешний коннектор
      `livechat|<config>|<line>|<user>`    — виджет сайта
    Для обоих случаев line_id — третий элемент (индекс 2). Если строка
    не похожа на entity_id открытой линии — возвращаем None.

    Используется как fallback к `session.CONFIG_ID`: Bitrix не всегда
    отдаёт блок `session` в `imopenlines.session.history.get`, и без этого
    fallback у диалогов остаётся `line_id = NULL`, из-за чего «Топ
    открытых линий» в дашборде остаётся пустым.
    """
    if not entity_id:
        return None
    parts = entity_id.split("|")
    if len(parts) < 3:
        return None
    head = parts[0].lower()
    if head not in {"imol", "livechat"}:
        return None
    candidate = parts[2].strip()
    return candidate or None


def _channel_from_entity_id(entity_id: str | None) -> ConversationChannel:
    """
    `chat.entity_id` для открытых линий:
      "livechat|<config>|<line>|<user>"   — виджет сайта
      "imol|<connector_id>|<line>|<user>" — внешний коннектор (telegram, whatsapp, ...)
    """
    if not entity_id:
        return ConversationChannel.other
    parts = entity_id.split("|")
    head = parts[0].lower()
    if head == "livechat":
        return ConversationChannel.livechat
    if head == "imol" and len(parts) >= 2:
        return map_connector_to_channel(parts[1])
    return map_connector_to_channel(head)


def _extract_contact(
    users: dict[str, Any] | None, chat_meta: dict[str, Any] | None
) -> tuple[str | None, str | None]:
    """Возвращает (contact_name, contact_external_id) — клиента из участников чата."""
    if not users:
        return (chat_meta or {}).get("name") if chat_meta else None, None
    # Клиент = пользователь с признаком connector/extranet/network.
    for uid, u in users.items():
        if not isinstance(u, dict):
            continue
        if u.get("connector") or u.get("extranet") or u.get("network"):
            return u.get("name"), str(uid)
    # Fallback — название чата.
    return (chat_meta or {}).get("name") if chat_meta else None, None


def _sender_type(msg: dict[str, Any], users: dict[str, Any] | None) -> SenderType:
    sender_id = str(msg.get("senderid") or msg.get("senderId") or msg.get("author_id") or "")
    if sender_id in {"0", ""}:
        return SenderType.system
    user = (users or {}).get(sender_id)
    if isinstance(user, dict):
        if user.get("bot"):
            return SenderType.bot
        if user.get("connector") or user.get("extranet") or user.get("network"):
            return SenderType.client
        return SenderType.agent
    return SenderType.agent


# Статусы сессии Open Channels в Bitrix24:
# 0 — новая, 20 — операторская, 25 — клиент ответил, 40 — оператор ответил,
# 60 — отслеживание, 65/70 — ответы после трекинга, 80 — закрыта, 90 — в архиве.
# Считаем сессию закрытой при STATUS >= 80.
_BITRIX_SESSION_CLOSED_STATUS = 80


def _session_meta(history: dict[str, Any]) -> tuple[str | None, str | None]:
    """Возвращает (operator_id, line_id) из блока session.

    Bitrix24 в `imopenlines.session.history.get`:
      session.OPERATOR_ID — оператор открытой линии (id Bitrix-пользователя)
      session.CONFIG_ID   — id открытой линии (config)
    Если блока нет — оба значения None.
    """
    session = history.get("session")
    if not isinstance(session, dict):
        return None, None

    def _g(*keys: str) -> str | None:
        for k in keys:
            v = session.get(k)
            if v not in (None, "", 0, "0"):
                return str(v)
        return None

    operator_id = _g("OPERATOR_ID", "operator_id")
    line_id = _g("CONFIG_ID", "config_id", "LINE_ID", "line_id")
    return operator_id, line_id


def _session_is_closed(history: dict[str, Any]) -> bool:
    """Определяет закрытость сессии Open Channels по полю STATUS.

    Bitrix24 в `imopenlines.session.history.get` возвращает блок `session`
    с числовым STATUS жизненного цикла. STATUS >= 80 — сессия завершена.

    Если STATUS не пришёл (старые API/частичные ответы), считаем диалог
    открытым — лучше показать активным, чем ошибочно закрыть.
    """
    session = history.get("session")
    if not isinstance(session, dict):
        return False
    raw_status = session.get("STATUS")
    if raw_status is None:
        raw_status = session.get("status")
    try:
        return int(raw_status) >= _BITRIX_SESSION_CLOSED_STATUS
    except (TypeError, ValueError):
        return False


@dataclass(slots=True)
class ImportStats:
    sessions: int = 0
    messages: int = 0
    skipped_chats: int = 0


async def _upsert_conversation(
    session: AsyncSession,
    integration: Integration,
    *,
    external_id: str,
    channel: ConversationChannel,
    contact_name: str | None,
    contact_external_id: str | None,
    is_closed: bool,
    assigned_user_id: str | None = None,
    line_id: str | None = None,
) -> Conversation:
    existing = await session.execute(
        select(Conversation).where(
            Conversation.integration_id == integration.id,
            Conversation.external_id == external_id,
        )
    )
    conv = existing.scalar_one_or_none()
    target_status = (
        ConversationStatus.closed if is_closed else ConversationStatus.open
    )
    if conv:
        if contact_name and not conv.contact_name:
            conv.contact_name = contact_name
        if contact_external_id and not conv.contact_external_id:
            conv.contact_external_id = contact_external_id
        if assigned_user_id and conv.assigned_user_id != assigned_user_id:
            conv.assigned_user_id = assigned_user_id
        if line_id and conv.line_id != line_id:
            conv.line_id = line_id
        # Синхронизируем статус в обе стороны: закрытый стал открытым (новое
        # сообщение в закрытый диалог) и наоборот.
        if conv.status != target_status:
            conv.status = target_status
            if target_status == ConversationStatus.closed and conv.closed_at is None:
                conv.closed_at = datetime.now(UTC)
            elif target_status == ConversationStatus.open:
                # Если диалог переоткрылся — closed_at сбрасываем; новый
                # closed_at установится при следующем закрытии.
                conv.closed_at = None
        return conv

    conv = Conversation(
        id=_new_id("conv"),
        integration_id=integration.id,
        external_id=external_id,
        channel=channel,
        contact_name=contact_name,
        contact_external_id=contact_external_id,
        status=target_status,
        assigned_user_id=assigned_user_id,
        line_id=line_id,
        closed_at=datetime.now(UTC) if is_closed else None,
    )
    session.add(conv)
    await session.flush()
    return conv


async def _recompute_conversation_analytics(
    session: AsyncSession, conv: Conversation
) -> None:
    """Пересчитывает first_message_at / first_agent_reply_at / response_time_sec.

    Считаем по фактическим сообщениям в БД (агрегирующий SELECT), чтобы цифры
    были консистентны даже после переимпорта или backfill'а.
    """
    from sqlalchemy import func as sa_func

    # Самое раннее клиентское сообщение.
    first_client = (
        await session.execute(
            select(sa_func.min(Message.sent_at)).where(
                Message.conversation_id == conv.id,
                Message.sender_type == SenderType.client,
            )
        )
    ).scalar_one_or_none()

    first_agent: datetime | None = None
    if first_client is not None:
        # Первый ответ оператора/бота ПОСЛЕ первого клиентского сообщения.
        first_agent = (
            await session.execute(
                select(sa_func.min(Message.sent_at)).where(
                    Message.conversation_id == conv.id,
                    Message.sender_type.in_([SenderType.agent, SenderType.bot]),
                    Message.sent_at >= first_client,
                )
            )
        ).scalar_one_or_none()

    conv.first_message_at = first_client
    conv.first_agent_reply_at = first_agent
    if first_client and first_agent:
        delta = (first_agent - first_client).total_seconds()
        conv.response_time_sec = max(0, int(delta))
    else:
        conv.response_time_sec = None

    # Денормализуем last_message_at + превью — это главный sort-ключ Inbox.
    # Дешевле один SELECT на conv, чем JOIN+GROUP BY на каждом запросе списка.
    last_row = (
        await session.execute(
            select(Message.sent_at, Message.text)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.sent_at.desc())
            .limit(1)
        )
    ).first()
    if last_row is not None:
        conv.last_message_at = last_row[0]
        text = last_row[1] or ""
        conv.last_message_preview = text[:200] if text else None
    else:
        conv.last_message_at = None
        conv.last_message_preview = None


async def _insert_messages(
    session: AsyncSession,
    conversation: Conversation,
    history: dict[str, Any],
) -> int:
    raw_messages = history.get("message") or history.get("messages") or {}
    users = history.get("users") or {}
    if not raw_messages:
        return 0

    # Достаём существующие external_id, чтобы не вставлять дубликаты.
    msg_ids = [str(mid) for mid in raw_messages.keys()]
    existing_rows = await session.execute(
        select(Message.external_id).where(
            Message.conversation_id == conversation.id,
            Message.external_id.in_(msg_ids),
        )
    )
    existing: set[str] = {r[0] for r in existing_rows.all() if r[0]}

    inserted = 0
    for mid, msg in raw_messages.items():
        if not isinstance(msg, dict):
            continue
        ext_id = str(mid)
        if ext_id in existing:
            continue
        sent_at = _parse_iso(msg.get("date")) or datetime.now(UTC)
        text = msg.get("text") or msg.get("textlegacy")
        params = msg.get("params") or {}
        attachments = None
        attach = params.get("attach") if isinstance(params, dict) else None
        files = params.get("fileId") if isinstance(params, dict) else None
        if attach or files:
            attachments = []
            if attach:
                attachments.append({"kind": "attach", "data": attach})
            if files:
                attachments.append({"kind": "fileId", "data": files})
        session.add(
            Message(
                id=_new_id("msg"),
                conversation_id=conversation.id,
                external_id=ext_id,
                sender_type=_sender_type(msg, users),
                sender_external_id=str(msg.get("senderid") or "") or None,
                text=text,
                attachments=attachments,
                sent_at=sent_at,
            )
        )
        inserted += 1
    return inserted


async def import_open_lines(
    client: BitrixClient,
    session: AsyncSession,
    integration: Integration,
    *,
    days: int = 30,
    chat_limit: int = 500,
) -> ImportStats:
    """
    Импортирует видимые Open-Channels чаты с активностью за последние `days` дней.
    Бросает `BitrixAPIError`, если API возвращает ошибку.
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)
    recent = await client.call("im.recent.get", {"ONLY_OPENLINES": "Y"})
    if not isinstance(recent, list):
        recent = []

    stats = ImportStats()
    crm_seen: dict[str, CrmEntity] = {}  # entity_id → CrmEntity, для последующего enrichment
    crm_kinds_seen: set = set()
    for entry in recent[:chat_limit]:
        if not isinstance(entry, dict):
            continue
        chat_id = entry.get("chat_id") or entry.get("chatId")
        if not chat_id:
            stats.skipped_chats += 1
            continue
        last_activity = _parse_iso(
            entry.get("date_last_activity") or entry.get("date_update")
        )
        if last_activity and last_activity < cutoff:
            continue

        try:
            history = await client.call(
                "imopenlines.session.history.get", {"CHAT_ID": int(chat_id)}
            )
        except BitrixAPIError as exc:
            logger.warning(
                "imopenlines.session.history.get failed chat_id=%s: %s",
                chat_id,
                exc,
            )
            stats.skipped_chats += 1
            continue
        if not isinstance(history, dict):
            stats.skipped_chats += 1
            continue

        chat_meta = (history.get("chat") or {}).get(str(chat_id), {}) if isinstance(
            history.get("chat"), dict
        ) else {}
        users = history.get("users") or {}
        contact_name, contact_external_id = _extract_contact(users, chat_meta)
        entity_id_raw = chat_meta.get("entityId") or chat_meta.get("entity_id")
        channel = _channel_from_entity_id(entity_id_raw)
        is_closed = _session_is_closed(history)
        operator_id, line_id = _session_meta(history)
        # Fallback: Bitrix24 не всегда отдаёт `session` блок в
        # imopenlines.session.history.get. ID линии при этом всегда есть в
        # `entityId` чата — парсим оттуда, чтобы дашборд «Топ линий» работал.
        if not line_id:
            line_id = _line_id_from_entity_id(entity_id_raw)

        conv = await _upsert_conversation(
            session,
            integration,
            external_id=str(chat_id),
            channel=channel,
            contact_name=contact_name,
            contact_external_id=contact_external_id,
            is_closed=is_closed,
            assigned_user_id=operator_id,
            line_id=line_id,
        )
        inserted = await _insert_messages(session, conv, history)
        await _recompute_conversation_analytics(session, conv)

        # CRM-привязки: парсим из session-блока, идемпотентно создаём
        # CrmEntity-заглушки и ConversationCrmLink. Детали (стадия, сумма)
        # подтянутся одним батчем после цикла.
        for kind, ext_id in extract_crm_refs_from_session(history):
            ent = await upsert_link(
                session, integration, conv, kind=kind, external_id=ext_id
            )
            crm_seen[ent.id] = ent
            crm_kinds_seen.add(kind)

        stats.sessions += 1
        stats.messages += inserted
        await session.flush()

    # Обогащаем CRM-сущности одним проходом: сначала справочник стадий,
    # затем детали Deal/Lead/Contact/Company. Ошибки REST не должны валить
    # импорт сообщений — логируем и продолжаем.
    if crm_seen:
        try:
            stage_index = await sync_stages_cache(
                client, session, integration, crm_kinds_seen
            )
            await enrich_entities(
                client,
                session,
                integration,
                list(crm_seen.values()),
                stage_index,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("CRM enrichment failed: %s", exc)

    await session.commit()
    return stats


async def run_import_job(
    client: BitrixClient,
    session: AsyncSession,
    job: ImportJob,
    integration: Integration,
) -> None:
    """Запускает импорт и обновляет `ImportJob` (status/счётчики/error)."""
    job.status = ImportJobStatus.running
    job.started_at = datetime.now(UTC)
    await session.flush()
    try:
        stats = await import_open_lines(
            client, session, integration, days=job.days
        )
        job.processed_sessions = stats.sessions
        job.processed_messages = stats.messages
        job.status = ImportJobStatus.done
    except Exception as exc:  # noqa: BLE001
        logger.exception("import job failed: %s", exc)
        job.status = ImportJobStatus.failed
        job.error = str(exc)[:1000]
    finally:
        job.finished_at = datetime.now(UTC)
        await session.commit()
