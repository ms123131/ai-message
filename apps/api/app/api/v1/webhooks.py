"""
Приёмник webhook-событий от внешних систем.

На MVP: только логируем входящий payload и кладём в очередь обработки (заглушка).
На фазе 2: подключим Redis Stream / Celery для асинхронной обработки.
"""

import logging

from fastapi import APIRouter, Request, status

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/bitrix24", status_code=status.HTTP_202_ACCEPTED)
async def bitrix24_webhook(request: Request) -> dict[str, str]:
    """
    Принимает события от Bitrix24 (OnImOpenLinesMessageAdd, OnCrmDealUpdate, …).

    Bitrix24 шлёт application/x-www-form-urlencoded с полями `event`, `data[...]`,
    `ts`, `auth[*]`. Возвращаем 202, реальная обработка — асинхронно.
    """
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        payload = await request.form()
        data = dict(payload)
    else:
        data = await request.json() if "json" in content_type else {}

    event = data.get("event", "<unknown>")
    application_token = data.get("auth[application_token]") or data.get(
        "application_token"
    )
    logger.info(
        "bitrix24 webhook received: event=%s domain=%s token=%s",
        event,
        data.get("auth[domain]"),
        "***" if application_token else None,
    )

    # TODO: валидация application_token, dedup по event_handler_id, постановка в очередь
    return {"status": "accepted", "event": str(event)}
