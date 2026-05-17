"""
Подписка на события Bitrix24 и парсинг входящих webhook-payload'ов.

Документация:
  https://apidocs.bitrix24.ru/api-reference/events/index.html
  https://apidocs.bitrix24.ru/api-reference/event-bind/index.html

Open Channels event payload (form-urlencoded):
  event=ONIMOPENLINESMESSAGEADD
  data[PARAMS][CHAT_ID]=12345
  data[PARAMS][MESSAGE]=Привет
  data[PARAMS][FROM_USER_ID]=42
  data[PARAMS][AUTHOR_ID]=42
  data[PARAMS][SESSION_ID]=999
  data[PARAMS][CONNECTOR][ID]=telegram
  data[PARAMS][CONNECTOR][CHAT_ID]=tg_chat_external
  ts=1717000000
  auth[domain]=portal.bitrix24.ru
  auth[member_id]=abcdef…
  auth[application_token]=…
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.db.models import ConversationChannel, SenderType

# Подписываемся на эти события при настройке интеграции.
SUPPORTED_EVENTS: tuple[str, ...] = (
    "OnImOpenLinesMessageAdd",
    "OnImOpenLinesSessionStart",
    "OnImOpenLinesSessionFinish",
)

# Маппинг id коннектора Open Channels → наш enum.
_CONNECTOR_TO_CHANNEL: dict[str, ConversationChannel] = {
    "whatsappbytwilio": ConversationChannel.whatsapp,
    "whatsapp": ConversationChannel.whatsapp,
    "wazzup24": ConversationChannel.whatsapp,
    "telegrambot": ConversationChannel.telegram,
    "telegram": ConversationChannel.telegram,
    "vkgroup": ConversationChannel.vk,
    "vk": ConversationChannel.vk,
    "instagram": ConversationChannel.instagram,
    "facebook": ConversationChannel.facebook,
    "fbinstagramdirect": ConversationChannel.instagram,
    "livechat": ConversationChannel.livechat,
    "network": ConversationChannel.livechat,
    "imessage": ConversationChannel.other,
}


def map_connector_to_channel(connector_id: str | None) -> ConversationChannel:
    if not connector_id:
        return ConversationChannel.other
    return _CONNECTOR_TO_CHANNEL.get(connector_id.lower(), ConversationChannel.other)


@dataclass(slots=True)
class ParsedMessageEvent:
    """Извлечённые поля из ONIMOPENLINESMESSAGEADD."""

    event: str
    domain: str | None
    member_id: str | None
    application_token: str | None
    chat_id: str
    message_id: str | None
    text: str
    sender_external_id: str | None
    sender_type: SenderType
    channel: ConversationChannel
    connector_chat_id: str | None
    sent_at: datetime
    raw: dict[str, Any] = field(repr=False)


def _flatten_form(payload: dict[str, Any]) -> dict[str, str]:
    """Bitrix24 шлёт form-encoded с `data[KEY][SUB]` — нормализуем в плоский dict."""
    return {k: str(v) for k, v in payload.items()}


def _g(d: dict[str, str], *keys: str) -> str | None:
    for k in keys:
        if k in d and d[k] != "":
            return d[k]
    return None


def parse_openlines_message(payload: dict[str, Any]) -> ParsedMessageEvent | None:
    """
    Парсит form-payload OnImOpenLinesMessageAdd.

    Возвращает None если событие не относится к сообщениям Open Channels.
    """
    flat = _flatten_form(payload)
    event = (flat.get("event") or "").upper()
    if event != "ONIMOPENLINESMESSAGEADD":
        return None

    chat_id = _g(flat, "data[PARAMS][CHAT_ID]", "data[CHAT][ID]", "data[CHAT_ID]")
    if not chat_id:
        return None

    text = _g(flat, "data[PARAMS][MESSAGE]", "data[MESSAGE]") or ""
    message_id = _g(flat, "data[PARAMS][ID]", "data[PARAMS][MESSAGE_ID]", "data[MESSAGE][ID]")
    sender_id = _g(
        flat,
        "data[PARAMS][AUTHOR_ID]",
        "data[PARAMS][FROM_USER_ID]",
        "data[USER][ID]",
    )
    connector_id = _g(
        flat,
        "data[PARAMS][CONNECTOR][ID]",
        "data[PARAMS][CHAT][CONNECTOR][ID]",
    )
    connector_chat_id = _g(flat, "data[PARAMS][CONNECTOR][CHAT_ID]")

    # Bitrix передаёт IS_OWN_MESSAGE: 'Y' — сообщение оператора (наш пользователь),
    # 'N' — сообщение клиента из канала.
    is_own = (_g(flat, "data[PARAMS][IS_OWN_MESSAGE]") or "N").upper() == "Y"
    sender_type = SenderType.agent if is_own else SenderType.client

    ts_raw = _g(flat, "ts", "data[PARAMS][DATE_CREATE]")
    sent_at = datetime.now(UTC)
    if ts_raw and ts_raw.isdigit():
        sent_at = datetime.fromtimestamp(int(ts_raw), tz=UTC)

    return ParsedMessageEvent(
        event=event,
        domain=_g(flat, "auth[domain]"),
        member_id=_g(flat, "auth[member_id]"),
        application_token=_g(flat, "auth[application_token]"),
        chat_id=str(chat_id),
        message_id=str(message_id) if message_id else None,
        text=text,
        sender_external_id=str(sender_id) if sender_id else None,
        sender_type=sender_type,
        channel=map_connector_to_channel(connector_id),
        connector_chat_id=connector_chat_id,
        sent_at=sent_at,
        raw=flat,
    )


async def bind_events(
    client,
    handler_url: str,
    events: tuple[str, ...] = SUPPORTED_EVENTS,
) -> list[dict[str, Any]]:
    """
    Регистрирует обработчик для каждого события через `event.bind`.

    Возвращает результаты вызовов — пригодится для отладки. Ошибки уже отдельных
    событий не валят всю операцию: бывают случаи, когда событие уже привязано
    (`error=ERROR_HANDLER_ALREADY_BINDED`).
    """
    from app.integrations.bitrix24.client import BitrixAPIError

    results: list[dict[str, Any]] = []
    for event in events:
        try:
            res = await client.call(
                "event.bind",
                {"event": event, "handler": handler_url},
            )
            results.append({"event": event, "result": res})
        except BitrixAPIError as exc:
            results.append({"event": event, "error": exc.error, "description": exc.description})
    return results


async def unbind_events(
    client,
    handler_url: str,
    events: tuple[str, ...] = SUPPORTED_EVENTS,
) -> list[dict[str, Any]]:
    from app.integrations.bitrix24.client import BitrixAPIError

    results: list[dict[str, Any]] = []
    for event in events:
        try:
            res = await client.call(
                "event.unbind",
                {"event": event, "handler": handler_url},
            )
            results.append({"event": event, "result": res})
        except BitrixAPIError as exc:
            results.append({"event": event, "error": exc.error, "description": exc.description})
    return results
