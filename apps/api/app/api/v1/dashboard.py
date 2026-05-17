"""Сводные метрики для дашборда (фаза 3.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.db.models import Conversation, ConversationChannel, Message

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DayPoint(BaseModel):
    day: str  # ISO дата YYYY-MM-DD
    count: int


class ChannelSlice(BaseModel):
    channel: ConversationChannel
    conversations: int
    messages: int


class DashboardStats(BaseModel):
    range_days: int
    range_from: datetime
    range_to: datetime
    total_conversations: int
    total_messages: int
    open_conversations: int
    volume_by_day: list[DayPoint]
    by_channel: list[ChannelSlice]


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    days: int = Query(14, ge=1, le=180),
    integration_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> DashboardStats:
    now = datetime.now(UTC)
    range_from = now - timedelta(days=days)

    conv_filter = []
    if integration_id:
        conv_filter.append(Conversation.integration_id == integration_id)

    # totals по диалогам
    conv_count_stmt = select(func.count(Conversation.id)).where(*conv_filter)
    open_count_stmt = select(func.count(Conversation.id)).where(
        Conversation.status == "open", *conv_filter
    )

    # totals по сообщениям в окне
    msg_window = (
        select(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.sent_at >= range_from, *conv_filter)
    )

    # объём по дням
    day_col = func.date(Message.sent_at).label("day")
    volume_stmt = (
        select(day_col, func.count(Message.id).label("cnt"))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Message.sent_at >= range_from, *conv_filter)
        .group_by(day_col)
        .order_by(day_col)
    )

    # разрез по каналам
    by_channel_stmt = (
        select(
            Conversation.channel,
            func.count(func.distinct(Conversation.id)).label("conv"),
            func.count(Message.id).label("msgs"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(*conv_filter)
        .group_by(Conversation.channel)
    )

    total_conv = (await session.execute(conv_count_stmt)).scalar_one()
    open_conv = (await session.execute(open_count_stmt)).scalar_one()
    total_msgs = (await session.execute(msg_window)).scalar_one()
    volume_rows = (await session.execute(volume_stmt)).all()
    channel_rows = (await session.execute(by_channel_stmt)).all()

    # Дополним нули за пропущенные дни, чтобы график был непрерывным.
    counts: dict[str, int] = {}
    for day, cnt in volume_rows:
        key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        counts[key] = int(cnt or 0)
    volume_by_day: list[DayPoint] = []
    for i in range(days):
        d = (range_from + timedelta(days=i)).date().isoformat()
        volume_by_day.append(DayPoint(day=d, count=counts.get(d, 0)))

    by_channel = [
        ChannelSlice(channel=ch, conversations=int(conv or 0), messages=int(msgs or 0))
        for ch, conv, msgs in channel_rows
    ]

    return DashboardStats(
        range_days=days,
        range_from=range_from,
        range_to=now,
        total_conversations=int(total_conv or 0),
        total_messages=int(total_msgs or 0),
        open_conversations=int(open_conv or 0),
        volume_by_day=volume_by_day,
        by_channel=by_channel,
    )
