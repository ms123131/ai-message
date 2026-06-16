"""Settings endpoints: компания, биллинг (витрина), UI-предпочтения.

Вкладки кабинета Settings:
- Компания: регион-настройки tenant'а (название, часовой пояс, язык).
- Оплата: ВИТРИНА тарифа + usage-счётчики + триал. Реального приёма платежей
  здесь нет — enforcement лимитов и платёжный провайдер вынесены в follow-up
  (planApp.md, трек F).
- UI-предпочтения: раскладка настраиваемого KPI-дашборда (per-user).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db import get_session
from app.db.models import (
    Conversation,
    Integration,
    Message,
    Tenant,
    User,
    UserRole,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Компания
# ---------------------------------------------------------------------------


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    timezone: str
    locale: str


class CompanyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=8)


@router.get("/company", response_model=CompanyOut)
async def get_company(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.patch("/company", response_model=CompanyOut)
async def update_company(
    body: CompanyPatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="admin role required")
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if body.name is not None:
        tenant.name = body.name
    if body.timezone is not None:
        tenant.timezone = body.timezone
    if body.locale is not None:
        tenant.locale = body.locale
    await session.commit()
    await session.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# Биллинг (витрина)
# ---------------------------------------------------------------------------

# Мягкие лимиты тарифов — пока только для отображения прогресс-баров usage,
# enforcement нет (follow-up F1). None = безлимит.
PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    "trial": {"conversations": 500, "messages": 5000, "integrations": 1},
    "start": {"conversations": 2000, "messages": 50000, "integrations": 2},
    "pro": {"conversations": 20000, "messages": 500000, "integrations": 10},
    "enterprise": {"conversations": None, "messages": None, "integrations": None},
}


class BillingUsage(BaseModel):
    conversations: int
    messages: int
    integrations: int


class BillingOut(BaseModel):
    plan: str
    trial_ends_at: datetime | None
    usage: BillingUsage
    limits: dict[str, int | None]


@router.get("/billing", response_model=BillingOut)
async def get_billing(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BillingOut:
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant_integration_ids = select(Integration.id).where(
        Integration.tenant_id == user.tenant_id
    )

    conversations = await session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.integration_id.in_(tenant_integration_ids))
    )
    messages = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.tenant_id == user.tenant_id)
    )
    integrations = await session.scalar(
        select(func.count())
        .select_from(Integration)
        .where(Integration.tenant_id == user.tenant_id)
    )

    limits = PLAN_LIMITS.get(tenant.plan, PLAN_LIMITS["trial"])
    return BillingOut(
        plan=tenant.plan,
        trial_ends_at=tenant.trial_ends_at,
        usage=BillingUsage(
            conversations=conversations or 0,
            messages=messages or 0,
            integrations=integrations or 0,
        ),
        limits=dict(limits),
    )


# ---------------------------------------------------------------------------
# UI-предпочтения (раскладка дашборда и т.п.)
# ---------------------------------------------------------------------------


class PreferencesIn(BaseModel):
    # Произвольный JSON-объект настроек UI. Мерж по верхним ключам.
    preferences: dict[str, Any]


class PreferencesOut(BaseModel):
    preferences: dict[str, Any]


@router.get("/preferences", response_model=PreferencesOut)
async def get_preferences(
    user: User = Depends(get_current_user),
) -> PreferencesOut:
    return PreferencesOut(preferences=user.ui_preferences or {})


@router.put("/preferences", response_model=PreferencesOut)
async def update_preferences(
    body: PreferencesIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PreferencesOut:
    merged: dict[str, Any] = dict(user.ui_preferences or {})
    merged.update(body.preferences)
    user.ui_preferences = merged
    await session.commit()
    return PreferencesOut(preferences=merged)
