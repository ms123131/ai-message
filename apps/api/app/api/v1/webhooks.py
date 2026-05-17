"""
Приёмник webhook-событий от Bitrix24.

Логика:
1. Принимаем form-encoded payload (B24 шлёт application/x-www-form-urlencoded).
2. По `auth[member_id]` (OAuth) или `auth[domain]` (webhook-режим) находим Integration.
3. Парсим `OnImOpenLinesMessageAdd` → upsert Conversation, insert Message с дедупом.
4. Возвращаем 202. Для неподдерживаемых событий — просто 202 без работы.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.db.models import Conversation, ConversationStatus, Integration, Message
from app.integrations.bitrix24.events import (
    ParsedMessageEvent,
    parse_openlines_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(8).lower()}"


async def _find_integration(
    session: AsyncSession, member_id: str | None, domain: str | None
) -> Integration | None:
    if member_id:
        result = await session.execute(
            select(Integration).where(Integration.member_id == member_id).limit(1)
        )
        obj = result.scalar_one_or_none()
        if obj:
            return obj
    if domain:
        result = await session.execute(
            select(Integration).where(Integration.domain == domain).limit(1)
        )
        return result.scalar_one_or_none()
    return None


async def _upsert_conversation(
    session: AsyncSession, integration: Integration, ev: ParsedMessageEvent
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.integration_id == integration.id,
            Conversation.external_id == ev.chat_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv:
        return conv
    conv = Conversation(
        id=_new_id("conv"),
        integration_id=integration.id,
        external_id=ev.chat_id,
        channel=ev.channel,
        contact_external_id=ev.connector_chat_id,
        status=ConversationStatus.open,
    )
    session.add(conv)
    await session.flush()
    return conv


async def _ingest_message_event(
    session: AsyncSession, integration: Integration, ev: ParsedMessageEvent
) -> Message | None:
    conv = await _upsert_conversation(session, integration, ev)
    msg = Message(
        id=_new_id("msg"),
        conversation_id=conv.id,
        external_id=ev.message_id,
        sender_type=ev.sender_type,
        sender_external_id=ev.sender_external_id,
        text=ev.text,
        sent_at=ev.sent_at,
    )
    session.add(msg)
    try:
        await session.flush()
    except IntegrityError:
        # Дубликат external_id внутри conversation — событие уже обработано.
        await session.rollback()
        return None
    return msg


@router.post("/bitrix24", status_code=status.HTTP_202_ACCEPTED)
async def bitrix24_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | None]:
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        payload = await request.form()
        data = dict(payload)
    elif "json" in content_type:
        data = await request.json()
    else:
        data = {}

    event = str(data.get("event", "")).upper()
    member_id = data.get("auth[member_id]") or (
        data.get("auth", {}).get("member_id") if isinstance(data.get("auth"), dict) else None
    )
    domain = data.get("auth[domain]") or (
        data.get("auth", {}).get("domain") if isinstance(data.get("auth"), dict) else None
    )

    logger.info("bitrix24 webhook: event=%s domain=%s member_id=%s", event, domain, member_id)

    integration = await _find_integration(session, member_id, domain)
    if not integration:
        logger.warning(
            "bitrix24 webhook: integration not found (member_id=%s domain=%s)",
            member_id,
            domain,
        )
        return {"status": "accepted", "event": event, "result": "no_integration"}

    parsed = parse_openlines_message(data)
    if not parsed:
        return {"status": "accepted", "event": event, "result": "unsupported"}

    msg = await _ingest_message_event(session, integration, parsed)
    if not msg:
        return {"status": "accepted", "event": event, "result": "duplicate"}

    await session.commit()
    return {
        "status": "accepted",
        "event": event,
        "result": "ingested",
        "message_id": msg.id,
    }
