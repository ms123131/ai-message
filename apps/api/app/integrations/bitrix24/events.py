"""
Подписка на события Bitrix24 и парсинг входящих webhook-payload'ов.

Документация:
  https://apidocs.bitrix24.ru/api-reference/events/index.html
  https://apidocs.bitrix24.ru/api-reference/event-bind/index.html
  https://apidocs.bitrix24.ru/api-reference/imopenlines/openlines/events/on-open-line-message-add.html

Open Channels event payload (form-urlencoded):
  event=ONOPENLINEMESSAGEADD
  eventId=1
  data[DATA][0][connector][connector_id]=livechat   # id коннектора (livechat, telegram, ...)
  data[DATA][0][connector][line_id]=128
  data[DATA][0][connector][chat_id]=10587           # chat_id во внешней системе
  data[DATA][0][connector][user_id]=1985            # user_id во внешней системе
  data[DATA][0][chat][id]=10585                     # chat_id внутри B24 (наш external_id)
  data[DATA][0][message][id]=80964
  data[DATA][0][message][date]=2026-05-17T19:28:18+03:00
  data[DATA][0][message][text]=hello
  data[DATA][0][message][system]=N
  data[DATA][0][message][user_id]=1985              # sender внутри B24
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
# Имена соответствуют актуальной документации B24 (без префикса `Im` и без `s` в `Line`).
SUPPORTED_EVENTS: tuple[str, ...] = (
    "OnOpenLineMessageAdd",
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
    line_id: str | None
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
    Парсит form-payload `OnOpenLineMessageAdd`.

    Bitrix24 шлёт несколько сообщений в одном hit через `data[DATA][N][...]`.
    Этот парсер берёт первое (N=0) — webhook-handler может вызвать парсер
    с разными префиксами при необходимости (TODO: пагинация по N).

    Возвращает None если событие не относится к сообщениям Open Channels.
    """
    flat = _flatten_form(payload)
    event = (flat.get("event") or "").upper()
    if event != "ONOPENLINEMESSAGEADD":
        return None

    p = "data[DATA][0]"  # префикс первого сообщения в пачке
    chat_id = _g(flat, f"{p}[chat][id]", f"{p}[CHAT][ID]")
    if not chat_id:
        return None

    text = _g(flat, f"{p}[message][text]", f"{p}[MESSAGE][TEXT]") or ""
    message_id = _g(flat, f"{p}[message][id]", f"{p}[MESSAGE][ID]")
    message_user_id = _g(flat, f"{p}[message][user_id]", f"{p}[MESSAGE][USER_ID]")
    is_system = (_g(flat, f"{p}[message][system]", f"{p}[MESSAGE][SYSTEM]") or "N").upper() == "Y"

    connector_id = _g(flat, f"{p}[connector][connector_id]", f"{p}[CONNECTOR][CONNECTOR_ID]")
    connector_chat_id = _g(flat, f"{p}[connector][chat_id]", f"{p}[CONNECTOR][CHAT_ID]")
    connector_user_id = _g(flat, f"{p}[connector][user_id]", f"{p}[CONNECTOR][USER_ID]")
    # `line_id` в payload вебхука — id открытой линии (CONFIG_ID). Без него
    # Telegram-диалоги хранились с line_id=NULL и проваливались из «Топ
    # открытых линий» на дашборде. Сессионный fallback (через session.history)
    # не всегда отдаёт session-блок именно для коннекторов вроде telegram.
    line_id = _g(
        flat,
        f"{p}[connector][line_id]",
        f"{p}[CONNECTOR][LINE_ID]",
        f"{p}[chat][line_id]",
        f"{p}[CHAT][LINE_ID]",
    )

    # Определяем тип отправителя:
    # - system=Y → системное сообщение от B24;
    # - message.user_id совпадает с connector.user_id → пишет клиент из внешнего канала;
    # - иначе → оператор внутри B24.
    if is_system:
        sender_type = SenderType.system
    elif message_user_id and connector_user_id and message_user_id == connector_user_id:
        sender_type = SenderType.client
    else:
        sender_type = SenderType.agent

    # Дата: пробуем ISO-дату из message, иначе ts события.
    raw_date = _g(flat, f"{p}[message][date]", f"{p}[MESSAGE][DATE]")
    sent_at = datetime.now(UTC)
    if raw_date:
        try:
            sent_at = datetime.fromisoformat(raw_date)
        except ValueError:
            pass
    else:
        ts_raw = _g(flat, "ts")
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
        sender_external_id=str(message_user_id) if message_user_id else None,
        sender_type=sender_type,
        channel=map_connector_to_channel(connector_id),
        connector_chat_id=connector_chat_id,
        line_id=str(line_id) if line_id else None,
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
