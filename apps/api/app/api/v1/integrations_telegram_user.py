"""API подключения личных аккаунтов Telegram через QR-логин.

Flow:
  1. POST /integrations/telegram-user/qr/start
     → создаёт Integration(kind=telegram_user, status=pending),
       возвращает {integration_id, qr_url, expires_in}.
  2. POST /integrations/telegram-user/{id}/qr/poll
     → возвращает один из state: waiting | requires_password | connected.
       На waiting — обновлённый qr_url (Telegram-токен живёт ~30с).
       На connected — IntegrationOut.
  3. POST /integrations/telegram-user/{id}/password { "password": "…" }
     → шаг 2FA (если qr/poll вернул requires_password).
  4. DELETE /integrations/{id}  (общий роутер) — log_out + удаление.

Архитектура контекста QR-сессии — in-process registry в
`app.integrations.telegram_user.qr_auth`. Это ограничивает API одним
uvicorn-инстансом до момента, когда подключение завершено и
StringSession уже в БД. См. PLAN_CONNECTORS.md §3.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.db import get_session
from app.db.models import (
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
)
from app.db.models import User as UserModel
from app.integrations.telegram_user import (
    QRSessionExpired,
    QRSessionNotFound,
    TelegramNotConfigured,
    confirm_password,
    poll_qr_session,
    start_qr_session,
    teardown_qr_session,
)
from app.integrations.telegram_user.qr_auth import take_session_blob
from app.schemas.integration import IntegrationOut
from app.security.audit import write_audit
from app.security.ratelimit import limiter

router = APIRouter(
    prefix="/integrations/telegram-user", tags=["integrations:telegram-user"]
)


# ---------- request/response модели ----------


class QRStartResponse(BaseModel):
    integration_id: str
    qr_url: str
    expires_in: int


class QRPollResponse(BaseModel):
    state: str  # waiting | requires_password | connected
    qr_url: str | None = None
    expires_in: int | None = None
    integration: IntegrationOut | None = None


class PasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=500)


# ---------- helpers ----------


async def _get_pending_owned(
    session: AsyncSession, integration_id: str, user: UserModel
) -> Integration:
    obj = await session.get(Integration, integration_id)
    if (
        obj is None
        or obj.tenant_id != user.tenant_id
        or obj.kind != IntegrationKind.telegram_user
    ):
        raise HTTPException(status_code=404, detail="Integration not found")
    return obj


def _handle_telethon_unavailable(exc: TelegramNotConfigured) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "telegram_not_configured",
            "message": str(exc) or "Telegram personal integration is disabled",
        },
    )


# ---------- endpoints ----------


@router.post("/qr/start", response_model=QRStartResponse)
@limiter.limit("10/minute")
async def qr_start(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> QRStartResponse:
    """Создать черновик Integration и запросить QR-токен у Telegram."""
    integration_id = uuid.uuid4().hex
    obj = Integration(
        id=integration_id,
        tenant_id=user.tenant_id,
        kind=IntegrationKind.telegram_user,
        mode=IntegrationMode.qr_link,
        label="Telegram (личный)",
        domain=f"tg-user:{integration_id[:12]}",
        status=IntegrationStatus.pending,
    )
    session.add(obj)
    await session.commit()

    try:
        qr = await start_qr_session(integration_id)
    except TelegramNotConfigured as exc:
        # удаляем созданный pending — без QR-токена он бесполезен
        await session.delete(obj)
        await session.commit()
        raise _handle_telethon_unavailable(exc) from exc
    except Exception as exc:
        await session.delete(obj)
        await session.commit()
        raise HTTPException(
            status_code=502,
            detail={"code": "telegram_unavailable", "message": str(exc)},
        ) from exc

    return QRStartResponse(
        integration_id=integration_id,
        qr_url=qr["qr_url"],
        expires_in=qr["expires_in"],
    )


@router.post("/{integration_id}/qr/poll", response_model=QRPollResponse)
@limiter.limit("60/minute")
async def qr_poll(
    integration_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> QRPollResponse:
    obj = await _get_pending_owned(session, integration_id, user)
    try:
        result = await poll_qr_session(integration_id)
    except QRSessionNotFound as exc:
        raise HTTPException(
            status_code=410,
            detail={"code": "qr_session_not_found"},
        ) from exc
    except QRSessionExpired as exc:
        raise HTTPException(
            status_code=410,
            detail={"code": "qr_session_expired"},
        ) from exc
    except TelegramNotConfigured as exc:
        raise _handle_telethon_unavailable(exc) from exc

    state = result.get("state")
    if state == "connected":
        return QRPollResponse(
            state="connected",
            integration=await _finalize_integration(
                session, obj, integration_id, request, user
            ),
        )
    if state == "requires_password":
        return QRPollResponse(state="requires_password")
    return QRPollResponse(
        state="waiting",
        qr_url=result.get("qr_url"),
        expires_in=result.get("expires_in"),
    )


@router.post("/{integration_id}/password", response_model=QRPollResponse)
@limiter.limit("10/minute")
async def submit_password(
    integration_id: str,
    body: PasswordIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> QRPollResponse:
    obj = await _get_pending_owned(session, integration_id, user)
    try:
        result = await confirm_password(integration_id, body.password)
    except QRSessionNotFound as exc:
        raise HTTPException(
            status_code=410, detail={"code": "qr_session_not_found"}
        ) from exc
    except QRSessionExpired as exc:
        raise HTTPException(
            status_code=410, detail={"code": "qr_session_expired"}
        ) from exc
    except TelegramNotConfigured as exc:
        raise _handle_telethon_unavailable(exc) from exc
    except Exception as exc:
        # неверный пароль или прочая ошибка sign_in
        raise HTTPException(
            status_code=400,
            detail={"code": "password_rejected", "message": str(exc)},
        ) from exc

    if result.get("state") != "connected":
        # confirm_password всегда либо connected, либо exception — на всякий
        return QRPollResponse(state=result.get("state", "waiting"))

    return QRPollResponse(
        state="connected",
        integration=await _finalize_integration(
            session, obj, integration_id, request, user
        ),
    )


async def _finalize_integration(
    session: AsyncSession,
    obj: Integration,
    integration_id: str,
    request: Request,
    user: UserModel,
) -> IntegrationOut:
    """Сохранить StringSession в БД, проставить status=connected, написать audit."""
    string_session, me = await take_session_blob(integration_id)

    obj.auth_blob = string_session
    obj.status = IntegrationStatus.connected
    obj.member_id = me.get("id") or None
    phone = me.get("phone")
    if phone:
        obj.domain = phone if phone.startswith("+") else f"+{phone}"
    full_name = " ".join(
        x for x in (me.get("first_name"), me.get("last_name")) if x
    ).strip()
    if full_name:
        obj.label = full_name
    elif me.get("username"):
        obj.label = f"@{me['username']}"

    await write_audit(
        session,
        action="integration.telegram_user.connect",
        tenant_id=user.tenant_id,
        user_id=user.id,
        target_type="integration",
        target_id=obj.id,
        request=request,
        meta={"telegram_user_id": obj.member_id},
    )
    await session.commit()
    await session.refresh(obj)

    # клиент Telethon больше не нужен в памяти — сессия в БД
    await teardown_qr_session(integration_id)

    return IntegrationOut.model_validate(obj)


__all__ = ["router"]
