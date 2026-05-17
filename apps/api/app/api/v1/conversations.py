"""Read-API для диалогов и сообщений (фаза 3.5, минимум для end-to-end тестов)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db import get_session
from app.db.models import Conversation, ConversationChannel, Integration, Message
from app.db.models import User as UserModel
from app.schemas.conversation import (
    ConversationListItem,
    ConversationOut,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationListItem])
async def list_conversations(
    integration_id: str | None = None,
    channel: ConversationChannel | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[ConversationListItem]:
    last_msg = (
        select(
            Message.conversation_id.label("conv_id"),
            func.count(Message.id).label("cnt"),
            func.max(Message.sent_at).label("last_at"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(Conversation, last_msg.c.cnt, last_msg.c.last_at)
        .join(Integration, Integration.id == Conversation.integration_id)
        .outerjoin(last_msg, last_msg.c.conv_id == Conversation.id)
        .where(Integration.tenant_id == user.tenant_id)
        .order_by(desc(func.coalesce(last_msg.c.last_at, Conversation.created_at)))
        .limit(limit)
        .offset(offset)
    )
    if integration_id:
        stmt = stmt.where(Conversation.integration_id == integration_id)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)

    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    conv_ids = [c.id for c, _, _ in rows]
    # Берём по одному превью на conversation — последнее сообщение.
    preview_stmt = (
        select(Message.conversation_id, Message.text, Message.sent_at)
        .where(Message.conversation_id.in_(conv_ids))
        .order_by(Message.conversation_id, desc(Message.sent_at))
    )
    previews: dict[str, str] = {}
    for conv_id, text, _ in (await session.execute(preview_stmt)).all():
        previews.setdefault(conv_id, (text or "")[:200])

    items: list[ConversationListItem] = []
    for conv, cnt, last_at in rows:
        items.append(
            ConversationListItem(
                **ConversationOut.model_validate(conv).model_dump(),
                message_count=int(cnt or 0),
                last_message_at=last_at,
                last_message_preview=previews.get(conv.id),
            )
        )
    return items


async def _get_owned_conv(
    session: AsyncSession, conversation_id: str, user: UserModel
) -> Conversation:
    obj = await session.get(Conversation, conversation_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    integration = await session.get(Integration, obj.integration_id)
    if not integration or integration.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return obj


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> Conversation:
    return await _get_owned_conv(session, conversation_id, user)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[Message]:
    await _get_owned_conv(session, conversation_id, user)
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sent_at)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
