"""Аналитический дашборд (фаза 4Б).

Восемь эндпоинтов:

  GET /dashboard/overview      — KPI с дельтами к предыдущему периоду
  GET /dashboard/timeline      — объём сообщений по дням
  GET /dashboard/by-channel    — разбивка по каналам (donut)
  GET /dashboard/by-manager    — таблица операторов (JOIN PortalUser)
  GET /dashboard/heatmap       — активность день_недели × час
  GET /dashboard/sla-breaches  — открытые диалоги без ответа > N минут
  GET /dashboard/top-contacts  — топ-N контактов по объёму
  GET /dashboard/portal-users  — справочник операторов

Все эндпоинты принимают одинаковые фильтры:
  days           — окно в днях (1..180; default 14)
  integration_id — конкретная интеграция или все
  channel        — конкретный канал
  operator_id    — конкретный оператор (assigned_user_id)

Старый `/dashboard/stats` сохранён как алиас на /overview + timeline + by-channel
для обратной совместимости со старым фронтом.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, and_, case, desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db import get_session
from app.db.models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Integration,
    Message,
    PortalUser,
    SenderType,
)
from app.db.models import User as UserModel

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# Общие фильтры
# ---------------------------------------------------------------------------


class _Filters:
    """Набор whereclause'ов для одного запроса.

    Применяется к таблице conversations. Все эндпоинты строят на базе этого.
    """

    def __init__(
        self,
        tenant_id: str,
        *,
        integration_id: str | None,
        channel: ConversationChannel | None,
        operator_id: str | None,
    ) -> None:
        self.conv_filters: list[Any] = [
            Conversation.integration_id.in_(
                select(Integration.id).where(Integration.tenant_id == tenant_id)
            )
        ]
        if integration_id:
            self.conv_filters.append(Conversation.integration_id == integration_id)
        if channel:
            self.conv_filters.append(Conversation.channel == channel)
        if operator_id:
            self.conv_filters.append(Conversation.assigned_user_id == operator_id)


def _filters_dep(
    integration_id: str | None = None,
    channel: ConversationChannel | None = None,
    operator_id: str | None = None,
    user: UserModel = Depends(get_current_user),
) -> _Filters:
    return _Filters(
        tenant_id=user.tenant_id,
        integration_id=integration_id,
        channel=channel,
        operator_id=operator_id,
    )


def _window(days: int) -> tuple[datetime, datetime]:
    """Окно [from, to) — to = now, from = now - days. Без обрезки до начала суток,
    чтобы дельты сравнивались точно по интервалу.
    """
    now = datetime.now(UTC)
    return now - timedelta(days=days), now


# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------


class KPI(BaseModel):
    value: float
    delta_pct: float | None  # % изменения к прошлому периоду; None если нет базы
    delta_abs: float | None  # абсолютная дельта


class OverviewResponse(BaseModel):
    range_days: int
    range_from: datetime
    range_to: datetime
    # Объёмы.
    conversations: KPI  # новые диалоги в окне
    messages: KPI  # всего сообщений в окне
    open_now: int  # сейчас открытых (без окна — снимок состояния)
    # Качество.
    frt_median_sec: KPI  # медиана First Response Time
    frt_p90_sec: KPI  # p90 FRT
    resolution_median_sec: KPI  # медиана resolution time
    # Контакты.
    unique_contacts: KPI
    returning_contacts_pct: KPI  # % контактов с >1 диалогом
    # Производные.
    avg_messages_per_conv: KPI


class DayPoint(BaseModel):
    day: date
    conversations: int
    messages: int


class TimelineResponse(BaseModel):
    range_days: int
    points: list[DayPoint]


class ChannelSlice(BaseModel):
    channel: ConversationChannel
    conversations: int
    messages: int


class ByChannelResponse(BaseModel):
    slices: list[ChannelSlice]


class ManagerRow(BaseModel):
    operator_id: str
    full_name: str | None
    avatar_url: str | None
    work_position: str | None
    email: str | None
    conversations: int  # всего диалогов с этим оператором за окно
    open_conversations: int
    frt_median_sec: int | None
    frt_p90_sec: int | None
    messages_sent: int  # сообщений от этого оператора


class ByManagerResponse(BaseModel):
    rows: list[ManagerRow]


class HeatmapCell(BaseModel):
    weekday: int  # 0 = понедельник, 6 = воскресенье
    hour: int  # 0..23
    count: int


class HeatmapResponse(BaseModel):
    cells: list[HeatmapCell]


class SLABreachItem(BaseModel):
    conversation_id: str
    contact_name: str | None
    channel: ConversationChannel
    minutes_waiting: int
    last_client_message_at: datetime
    operator_id: str | None
    operator_name: str | None


class SLABreachesResponse(BaseModel):
    threshold_minutes: int
    items: list[SLABreachItem]


class TopContactItem(BaseModel):
    contact_external_id: str | None
    contact_name: str | None
    conversations: int
    messages: int
    last_message_at: datetime | None


class TopContactsResponse(BaseModel):
    items: list[TopContactItem]


class PortalUserOut(BaseModel):
    external_id: str
    full_name: str | None
    email: str | None
    work_position: str | None
    avatar_url: str | None
    is_active: bool


# ---------------------------------------------------------------------------
# Утилиты вычислений
# ---------------------------------------------------------------------------


def _kpi(current: float, previous: float | None) -> KPI:
    if previous is None or previous == 0:
        return KPI(
            value=current,
            delta_pct=None if not previous else 0.0,
            delta_abs=None if previous is None else current - previous,
        )
    delta_abs = current - previous
    delta_pct = (delta_abs / previous) * 100.0
    return KPI(value=current, delta_pct=delta_pct, delta_abs=delta_abs)


async def _scalar_or_zero(session: AsyncSession, stmt: Select) -> float:
    val = (await session.execute(stmt)).scalar_one_or_none()
    return float(val) if val is not None else 0.0


def _day_expr(column: Any, dialect: str) -> Any:
    """Усечение datetime до YYYY-MM-DD строки.

    Postgres: `to_char(col, 'YYYY-MM-DD')` — стабильно для TZ-aware.
    SQLite: `strftime('%Y-%m-%d', col)` — работает с ISO-строками
    (включая +00:00 и микросекунды).
    """
    if dialect == "postgresql":
        return func.to_char(column, "YYYY-MM-DD")
    return func.strftime("%Y-%m-%d", column)


def _percentile_expr(column: Any, fraction: float, dialect: str) -> Any:
    """Подбираем выражение для percentile в зависимости от диалекта.

    Postgres: percentile_cont(<fraction>) WITHIN GROUP (ORDER BY column).
    SQLite (тесты): фоллбек на AVG — точное p50/p90 для SQLite требовало бы
    оконных функций; для тестов достаточно нечисленной устойчивости.
    """
    if dialect == "postgresql":
        return func.percentile_cont(fraction).within_group(column)
    return func.avg(column)


# ---------------------------------------------------------------------------
# /overview
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    days: int = Query(14, ge=1, le=180),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> OverviewResponse:
    range_from, range_to = _window(days)
    prev_from = range_from - timedelta(days=days)
    prev_to = range_from
    dialect = session.bind.dialect.name if session.bind else "postgresql"

    async def conversations_in(start: datetime, end: datetime) -> float:
        stmt = select(func.count(Conversation.id)).where(
            *filters.conv_filters,
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
        return await _scalar_or_zero(session, stmt)

    async def messages_in(start: datetime, end: datetime) -> float:
        stmt = (
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(*filters.conv_filters, Message.sent_at >= start, Message.sent_at < end)
        )
        return await _scalar_or_zero(session, stmt)

    async def frt_stats(
        start: datetime, end: datetime, fraction: float
    ) -> float:
        expr = _percentile_expr(Conversation.response_time_sec, fraction, dialect)
        stmt = select(expr).where(
            *filters.conv_filters,
            Conversation.response_time_sec.is_not(None),
            Conversation.first_message_at >= start,
            Conversation.first_message_at < end,
        )
        return await _scalar_or_zero(session, stmt)

    async def resolution_median(start: datetime, end: datetime) -> float:
        delta_sec = func.extract(
            "epoch", Conversation.closed_at - Conversation.first_message_at
        )
        expr = _percentile_expr(delta_sec, 0.5, dialect)
        stmt = select(expr).where(
            *filters.conv_filters,
            Conversation.closed_at.is_not(None),
            Conversation.first_message_at.is_not(None),
            Conversation.closed_at >= start,
            Conversation.closed_at < end,
        )
        # extract('epoch', interval) — Postgres-only. На SQLite используем
        # julianday-разницу * 86400.
        if dialect != "postgresql":
            jd_diff = (
                func.julianday(Conversation.closed_at)
                - func.julianday(Conversation.first_message_at)
            ) * 86400
            stmt = select(func.avg(jd_diff)).where(
                *filters.conv_filters,
                Conversation.closed_at.is_not(None),
                Conversation.first_message_at.is_not(None),
                Conversation.closed_at >= start,
                Conversation.closed_at < end,
            )
        return await _scalar_or_zero(session, stmt)

    async def unique_contacts_in(start: datetime, end: datetime) -> float:
        stmt = select(
            func.count(distinct(Conversation.contact_external_id))
        ).where(
            *filters.conv_filters,
            Conversation.contact_external_id.is_not(None),
            Conversation.created_at >= start,
            Conversation.created_at < end,
        )
        return await _scalar_or_zero(session, stmt)

    async def returning_pct(start: datetime, end: datetime) -> float:
        # Доля контактов с >1 диалогом за окно.
        subq = (
            select(
                Conversation.contact_external_id.label("cid"),
                func.count(Conversation.id).label("cnt"),
            )
            .where(
                *filters.conv_filters,
                Conversation.contact_external_id.is_not(None),
                Conversation.created_at >= start,
                Conversation.created_at < end,
            )
            .group_by(Conversation.contact_external_id)
            .subquery()
        )
        total = (
            await session.execute(select(func.count()).select_from(subq))
        ).scalar_one()
        if not total:
            return 0.0
        returning = (
            await session.execute(
                select(func.count()).select_from(subq).where(subq.c.cnt > 1)
            )
        ).scalar_one()
        return (returning / total) * 100.0

    open_now_stmt = select(func.count(Conversation.id)).where(
        *filters.conv_filters,
        Conversation.status == ConversationStatus.open,
    )
    open_now = int((await session.execute(open_now_stmt)).scalar_one() or 0)

    cur_convs = await conversations_in(range_from, range_to)
    prev_convs = await conversations_in(prev_from, prev_to)
    cur_msgs = await messages_in(range_from, range_to)
    prev_msgs = await messages_in(prev_from, prev_to)
    cur_frt_med = await frt_stats(range_from, range_to, 0.5)
    prev_frt_med = await frt_stats(prev_from, prev_to, 0.5)
    cur_frt_p90 = await frt_stats(range_from, range_to, 0.9)
    prev_frt_p90 = await frt_stats(prev_from, prev_to, 0.9)
    cur_res = await resolution_median(range_from, range_to)
    prev_res = await resolution_median(prev_from, prev_to)
    cur_uniq = await unique_contacts_in(range_from, range_to)
    prev_uniq = await unique_contacts_in(prev_from, prev_to)
    cur_ret = await returning_pct(range_from, range_to)
    prev_ret = await returning_pct(prev_from, prev_to)

    avg_now = cur_msgs / cur_convs if cur_convs else 0.0
    avg_prev = prev_msgs / prev_convs if prev_convs else 0.0

    return OverviewResponse(
        range_days=days,
        range_from=range_from,
        range_to=range_to,
        conversations=_kpi(cur_convs, prev_convs),
        messages=_kpi(cur_msgs, prev_msgs),
        open_now=open_now,
        frt_median_sec=_kpi(cur_frt_med, prev_frt_med),
        frt_p90_sec=_kpi(cur_frt_p90, prev_frt_p90),
        resolution_median_sec=_kpi(cur_res, prev_res),
        unique_contacts=_kpi(cur_uniq, prev_uniq),
        returning_contacts_pct=_kpi(cur_ret, prev_ret),
        avg_messages_per_conv=_kpi(avg_now, avg_prev),
    )


# ---------------------------------------------------------------------------
# /timeline
# ---------------------------------------------------------------------------


@router.get("/timeline", response_model=TimelineResponse)
async def timeline(
    days: int = Query(14, ge=1, le=180),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    range_from, _ = _window(days)
    dialect = session.bind.dialect.name if session.bind else "postgresql"

    day_msg = _day_expr(Message.sent_at, dialect).label("day")
    msgs_stmt = (
        select(day_msg, func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*filters.conv_filters, Message.sent_at >= range_from)
        .group_by(day_msg)
    )
    day_conv = _day_expr(Conversation.created_at, dialect).label("day")
    convs_stmt = (
        select(day_conv, func.count(Conversation.id))
        .where(*filters.conv_filters, Conversation.created_at >= range_from)
        .group_by(day_conv)
    )

    msg_counts: dict[str, int] = {
        str(d): int(cnt or 0)
        for d, cnt in (await session.execute(msgs_stmt)).all()
    }
    conv_counts: dict[str, int] = {
        str(d): int(cnt or 0)
        for d, cnt in (await session.execute(convs_stmt)).all()
    }

    # Точки идут с (today - days + 1) по today включительно — итого `days` дней.
    today = datetime.now(UTC).date()
    points: list[DayPoint] = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        key = d.isoformat()
        points.append(
            DayPoint(
                day=d,
                conversations=conv_counts.get(key, 0),
                messages=msg_counts.get(key, 0),
            )
        )
    return TimelineResponse(range_days=days, points=points)


# ---------------------------------------------------------------------------
# /by-channel
# ---------------------------------------------------------------------------


@router.get("/by-channel", response_model=ByChannelResponse)
async def by_channel(
    days: int = Query(14, ge=1, le=180),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> ByChannelResponse:
    range_from, _ = _window(days)

    # Сначала диалоги за окно по каналам.
    conv_stmt = (
        select(Conversation.channel, func.count(Conversation.id))
        .where(*filters.conv_filters, Conversation.created_at >= range_from)
        .group_by(Conversation.channel)
    )
    msg_stmt = (
        select(Conversation.channel, func.count(Message.id))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(*filters.conv_filters, Message.sent_at >= range_from)
        .group_by(Conversation.channel)
    )

    conv_by: dict[ConversationChannel, int] = {
        ch: int(cnt or 0)
        for ch, cnt in (await session.execute(conv_stmt)).all()
    }
    msg_by: dict[ConversationChannel, int] = {
        ch: int(cnt or 0)
        for ch, cnt in (await session.execute(msg_stmt)).all()
    }
    all_channels = set(conv_by) | set(msg_by)
    slices = [
        ChannelSlice(
            channel=ch,
            conversations=conv_by.get(ch, 0),
            messages=msg_by.get(ch, 0),
        )
        for ch in all_channels
    ]
    slices.sort(key=lambda s: s.messages, reverse=True)
    return ByChannelResponse(slices=slices)


# ---------------------------------------------------------------------------
# /by-manager
# ---------------------------------------------------------------------------


@router.get("/by-manager", response_model=ByManagerResponse)
async def by_manager(
    days: int = Query(14, ge=1, le=180),
    limit: int = Query(50, ge=1, le=200),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> ByManagerResponse:
    range_from, _ = _window(days)
    dialect = session.bind.dialect.name if session.bind else "postgresql"

    # Базовая агрегация: по assigned_user_id за окно. CASE(...) работает
    # одинаково в Postgres и SQLite — не уходим в func.sum(bool).
    opens_case = func.sum(
        case(
            (Conversation.status == ConversationStatus.open, 1), else_=0
        )
    ).label("opens")
    conv_agg = (
        select(
            Conversation.integration_id.label("integration_id"),
            Conversation.assigned_user_id.label("operator_id"),
            func.count(Conversation.id).label("convs"),
            opens_case,
            _percentile_expr(
                Conversation.response_time_sec, 0.5, dialect
            ).label("frt_med"),
            _percentile_expr(
                Conversation.response_time_sec, 0.9, dialect
            ).label("frt_p90"),
        )
        .where(
            *filters.conv_filters,
            Conversation.assigned_user_id.is_not(None),
            Conversation.created_at >= range_from,
        )
        .group_by(Conversation.integration_id, Conversation.assigned_user_id)
    )

    rows = (await session.execute(conv_agg)).all()
    if not rows:
        return ByManagerResponse(rows=[])

    # Подтянем имена/аватары из PortalUser одним запросом.
    pairs = [(r.integration_id, r.operator_id) for r in rows]
    portal_users = (
        await session.execute(
            select(PortalUser).where(
                PortalUser.integration_id.in_({p[0] for p in pairs}),
                PortalUser.external_id.in_({p[1] for p in pairs}),
            )
        )
    ).scalars().all()
    pu_index = {(pu.integration_id, pu.external_id): pu for pu in portal_users}

    # Сообщений от оператора за окно.
    msgs_stmt = (
        select(
            Conversation.integration_id,
            Message.sender_external_id,
            func.count(Message.id),
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            *filters.conv_filters,
            Message.sender_type == SenderType.agent,
            Message.sender_external_id.is_not(None),
            Message.sent_at >= range_from,
        )
        .group_by(Conversation.integration_id, Message.sender_external_id)
    )
    msgs_index: dict[tuple[str, str], int] = {
        (intg, op): int(cnt or 0)
        for intg, op, cnt in (await session.execute(msgs_stmt)).all()
    }

    result_rows: list[ManagerRow] = []
    for r in rows:
        pu = pu_index.get((r.integration_id, r.operator_id))
        result_rows.append(
            ManagerRow(
                operator_id=r.operator_id,
                full_name=pu.full_name if pu else None,
                avatar_url=pu.avatar_url if pu else None,
                work_position=pu.work_position if pu else None,
                email=pu.email if pu else None,
                conversations=int(r.convs or 0),
                open_conversations=int(r.opens or 0),
                frt_median_sec=int(r.frt_med) if r.frt_med is not None else None,
                frt_p90_sec=int(r.frt_p90) if r.frt_p90 is not None else None,
                messages_sent=msgs_index.get(
                    (r.integration_id, r.operator_id), 0
                ),
            )
        )
    result_rows.sort(key=lambda x: x.conversations, reverse=True)
    return ByManagerResponse(rows=result_rows[:limit])


# ---------------------------------------------------------------------------
# /heatmap
# ---------------------------------------------------------------------------


@router.get("/heatmap", response_model=HeatmapResponse)
async def heatmap(
    days: int = Query(30, ge=1, le=180),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> HeatmapResponse:
    range_from, _ = _window(days)
    dialect = session.bind.dialect.name if session.bind else "postgresql"

    if dialect == "postgresql":
        # extract: dow → 0..6 (вс=0). Конвертируем в 0..6 (пн=0).
        dow = ((func.extract("dow", Message.sent_at) + 6) % 7).label("wd")
        hr = func.extract("hour", Message.sent_at).label("hr")
    else:
        # SQLite: strftime %w (вс=0); +6 mod 7 → пн=0.
        dow = (
            (func.cast(func.strftime("%w", Message.sent_at), type_=func.count.type) + 6)
            % 7
        ).label("wd")
        hr = func.cast(func.strftime("%H", Message.sent_at), type_=func.count.type).label("hr")

    stmt = (
        select(dow, hr, func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(*filters.conv_filters, Message.sent_at >= range_from)
        .group_by(dow, hr)
    )
    cells = [
        HeatmapCell(weekday=int(wd or 0), hour=int(hr or 0), count=int(cnt or 0))
        for wd, hr, cnt in (await session.execute(stmt)).all()
    ]
    return HeatmapResponse(cells=cells)


# ---------------------------------------------------------------------------
# /sla-breaches
# ---------------------------------------------------------------------------


@router.get("/sla-breaches", response_model=SLABreachesResponse)
async def sla_breaches(
    threshold_minutes: int = Query(15, ge=1, le=1440),
    limit: int = Query(50, ge=1, le=200),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> SLABreachesResponse:
    """Открытые диалоги, где последнее сообщение клиента ожидает ответа > threshold.

    Логика: для каждого открытого диалога находим последнее клиентское
    сообщение; если после него нет ни одного сообщения оператора/бота
    и прошло > threshold_minutes — это нарушение SLA.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(minutes=threshold_minutes)

    # Подзапрос: последнее сообщение в каждом открытом диалоге.
    last_msg_sq = (
        select(
            Message.conversation_id.label("cid"),
            func.max(Message.sent_at).label("last_ts"),
        )
        .group_by(Message.conversation_id)
        .subquery()
    )

    # Последнее сообщение — клиентское, и оно старше cutoff.
    stmt = (
        select(Conversation, Message, last_msg_sq.c.last_ts)
        .join(last_msg_sq, last_msg_sq.c.cid == Conversation.id)
        .join(
            Message,
            and_(
                Message.conversation_id == Conversation.id,
                Message.sent_at == last_msg_sq.c.last_ts,
            ),
        )
        .where(
            *filters.conv_filters,
            Conversation.status == ConversationStatus.open,
            Message.sender_type == SenderType.client,
            Message.sent_at < cutoff,
        )
        .order_by(Message.sent_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return SLABreachesResponse(threshold_minutes=threshold_minutes, items=[])

    # Подтянем имена операторов одним запросом.
    integration_ids = {conv.integration_id for conv, _, _ in rows}
    operator_ids = {
        conv.assigned_user_id for conv, _, _ in rows if conv.assigned_user_id
    }
    pu_index: dict[tuple[str, str], PortalUser] = {}
    if operator_ids:
        pus = (
            await session.execute(
                select(PortalUser).where(
                    PortalUser.integration_id.in_(integration_ids),
                    PortalUser.external_id.in_(operator_ids),
                )
            )
        ).scalars().all()
        pu_index = {(p.integration_id, p.external_id): p for p in pus}

    items: list[SLABreachItem] = []
    for conv, last_msg, last_ts in rows:
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        minutes_waiting = int((now - last_ts).total_seconds() // 60)
        op_name: str | None = None
        if conv.assigned_user_id:
            pu = pu_index.get((conv.integration_id, conv.assigned_user_id))
            op_name = pu.full_name if pu else None
        items.append(
            SLABreachItem(
                conversation_id=conv.id,
                contact_name=conv.contact_name,
                channel=conv.channel,
                minutes_waiting=minutes_waiting,
                last_client_message_at=last_ts,
                operator_id=conv.assigned_user_id,
                operator_name=op_name,
            )
        )
    return SLABreachesResponse(threshold_minutes=threshold_minutes, items=items)


# ---------------------------------------------------------------------------
# /top-contacts
# ---------------------------------------------------------------------------


@router.get("/top-contacts", response_model=TopContactsResponse)
async def top_contacts(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    filters: _Filters = Depends(_filters_dep),
    session: AsyncSession = Depends(get_session),
) -> TopContactsResponse:
    range_from, _ = _window(days)

    stmt = (
        select(
            Conversation.contact_external_id,
            func.max(Conversation.contact_name).label("name"),
            func.count(distinct(Conversation.id)).label("convs"),
            func.count(Message.id).label("msgs"),
            func.max(Message.sent_at).label("last"),
        )
        .join(Message, Message.conversation_id == Conversation.id, isouter=True)
        .where(
            *filters.conv_filters,
            Conversation.contact_external_id.is_not(None),
            Conversation.created_at >= range_from,
        )
        .group_by(Conversation.contact_external_id)
        .order_by(desc("msgs"))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        TopContactItem(
            contact_external_id=cid,
            contact_name=name,
            conversations=int(convs or 0),
            messages=int(msgs or 0),
            last_message_at=last,
        )
        for cid, name, convs, msgs, last in rows
    ]
    return TopContactsResponse(items=items)


# ---------------------------------------------------------------------------
# /portal-users
# ---------------------------------------------------------------------------


@router.get("/portal-users", response_model=list[PortalUserOut])
async def portal_users_list(
    integration_id: str | None = None,
    only_active: bool = True,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PortalUserOut]:
    """Справочник операторов подключённых порталов (для фильтра по менеджеру).

    Изоляция: возвращаем только пользователей тех интеграций, что
    принадлежат tenant'у текущего пользователя.
    """
    tenant_ints = select(Integration.id).where(Integration.tenant_id == user.tenant_id)
    filters_: list[Any] = [PortalUser.integration_id.in_(tenant_ints)]
    if integration_id:
        filters_.append(PortalUser.integration_id == integration_id)
    if only_active:
        filters_.append(PortalUser.is_active.is_(True))

    rows = (
        await session.execute(
            select(PortalUser).where(*filters_).order_by(PortalUser.full_name)
        )
    ).scalars().all()
    return [
        PortalUserOut(
            external_id=p.external_id,
            full_name=p.full_name,
            email=p.email,
            work_position=p.work_position,
            avatar_url=p.avatar_url,
            is_active=p.is_active,
        )
        for p in rows
    ]


# ---------------------------------------------------------------------------
# Алиас старого /stats для обратной совместимости со старым фронтом
# ---------------------------------------------------------------------------


class DayPointLegacy(BaseModel):
    day: str
    count: int


class DashboardStats(BaseModel):
    range_days: int
    range_from: datetime
    range_to: datetime
    total_conversations: int
    total_messages: int
    open_conversations: int
    volume_by_day: list[DayPointLegacy]
    by_channel: list[ChannelSlice]


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats_legacy(
    days: int = Query(14, ge=1, le=180),
    integration_id: str | None = None,
    user: UserModel = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DashboardStats:
    """Старая ручка — оставлена для текущего фронта; перепишется в фазе 4В."""
    filters = _Filters(
        tenant_id=user.tenant_id,
        integration_id=integration_id,
        channel=None,
        operator_id=None,
    )
    range_from, range_to = _window(days)

    total_conv = int(
        (
            await session.execute(
                select(func.count(Conversation.id)).where(*filters.conv_filters)
            )
        ).scalar_one()
        or 0
    )
    open_conv = int(
        (
            await session.execute(
                select(func.count(Conversation.id)).where(
                    *filters.conv_filters,
                    Conversation.status == ConversationStatus.open,
                )
            )
        ).scalar_one()
        or 0
    )
    total_msgs = int(
        (
            await session.execute(
                select(func.count(Message.id))
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(*filters.conv_filters, Message.sent_at >= range_from)
            )
        ).scalar_one()
        or 0
    )

    dialect = session.bind.dialect.name if session.bind else "postgresql"
    day_col = _day_expr(Message.sent_at, dialect).label("day")
    volume_rows = (
        await session.execute(
            select(day_col, func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(*filters.conv_filters, Message.sent_at >= range_from)
            .group_by(day_col)
            .order_by(day_col)
        )
    ).all()
    counts: dict[str, int] = {str(day): int(cnt or 0) for day, cnt in volume_rows}
    volume_by_day = [
        DayPointLegacy(
            day=(range_from + timedelta(days=i)).date().isoformat(),
            count=counts.get(
                (range_from + timedelta(days=i)).date().isoformat(), 0
            ),
        )
        for i in range(days)
    ]

    by_channel_rows = (
        await session.execute(
            select(
                Conversation.channel,
                func.count(distinct(Conversation.id)).label("conv"),
                func.count(Message.id).label("msgs"),
            )
            .outerjoin(Message, Message.conversation_id == Conversation.id)
            .where(*filters.conv_filters)
            .group_by(Conversation.channel)
        )
    ).all()
    by_channel_list = [
        ChannelSlice(
            channel=ch, conversations=int(conv or 0), messages=int(msgs or 0)
        )
        for ch, conv, msgs in by_channel_rows
    ]

    return DashboardStats(
        range_days=days,
        range_from=range_from,
        range_to=range_to,
        total_conversations=total_conv,
        total_messages=total_msgs,
        open_conversations=open_conv,
        volume_by_day=volume_by_day,
        by_channel=by_channel_list,
    )
