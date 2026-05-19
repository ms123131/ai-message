"""CRUD для SLA-таргетов (фаза 5D).

Один tenant имеет:
- один глобальный таргет (channel=NULL) — дефолт для всех каналов
- опционально per-channel переопределения (channel = whatsapp/telegram/…)

Эндпоинты используют upsert по уникальному ключу (tenant_id, channel).
"""

from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db import get_session
from app.db.models import ConversationChannel, SLATarget
from app.db.models import User as UserModel

router = APIRouter(prefix="/sla-targets", tags=["sla-targets"])

# Дефолт для нового tenant'а, если нет ни одной записи.
DEFAULT_THRESHOLD_MINUTES = 15


class SLATargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    channel: ConversationChannel | None
    threshold_minutes: int


class SLATargetUpsert(BaseModel):
    channel: ConversationChannel | None = None
    threshold_minutes: int = Field(ge=1, le=1440 * 7)


@router.get("", response_model=list[SLATargetOut])
async def list_sla_targets(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[SLATargetOut]:
    rows = (
        await session.execute(
            select(SLATarget)
            .where(SLATarget.tenant_id == user.tenant_id)
            .order_by(SLATarget.channel.is_(None).desc(), SLATarget.channel)
        )
    ).scalars().all()
    # Если у tenant'а нет ни одной записи — отдаём дефолт.
    if not rows:
        return [SLATargetOut(channel=None, threshold_minutes=DEFAULT_THRESHOLD_MINUTES)]
    return [SLATargetOut.model_validate(r) for r in rows]


@router.put("", response_model=SLATargetOut)
async def upsert_sla_target(
    body: SLATargetUpsert,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> SLATargetOut:
    existing = (
        await session.execute(
            select(SLATarget).where(
                SLATarget.tenant_id == user.tenant_id,
                SLATarget.channel == body.channel,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.threshold_minutes = body.threshold_minutes
        target = existing
    else:
        target = SLATarget(
            id=f"sla_{secrets.token_urlsafe(8).lower()}",
            tenant_id=user.tenant_id,
            channel=body.channel,
            threshold_minutes=body.threshold_minutes,
        )
        session.add(target)
    await session.commit()
    await session.refresh(target)
    return SLATargetOut.model_validate(target)


@router.delete("", status_code=204)
async def delete_sla_target(
    channel: ConversationChannel | None = None,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> None:
    """Удаляет per-channel переопределение (или глобальный таргет).

    После удаления глобального будет применяться `DEFAULT_THRESHOLD_MINUTES`.
    """
    obj = (
        await session.execute(
            select(SLATarget).where(
                SLATarget.tenant_id == user.tenant_id,
                SLATarget.channel == channel,
            )
        )
    ).scalar_one_or_none()
    if not obj:
        raise HTTPException(status_code=404, detail="SLA target not found")
    await session.delete(obj)
    await session.commit()


async def resolve_thresholds(
    session: AsyncSession, tenant_id: str
) -> dict[ConversationChannel | None, int]:
    """Возвращает {channel: threshold_minutes} для всех каналов.

    Структура:
      None -> глобальный дефолт (или DEFAULT_THRESHOLD_MINUTES если не задан)
      ConversationChannel -> переопределение для канала, если есть

    sla-breaches берёт эту таблицу и применяет.
    """
    rows = (
        await session.execute(
            select(SLATarget).where(SLATarget.tenant_id == tenant_id)
        )
    ).scalars().all()
    result: dict[ConversationChannel | None, int] = {}
    for r in rows:
        result[r.channel] = r.threshold_minutes
    if None not in result:
        result[None] = DEFAULT_THRESHOLD_MINUTES
    return result
