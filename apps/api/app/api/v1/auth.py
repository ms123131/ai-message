"""Auth endpoints: register, login, refresh, logout, me."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.auth.security import (
    REFRESH_TTL,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import get_settings
from app.db import get_session
from app.db.models import AuthTokenType, Tenant, User, UserRole
from app.email.tokens import consume_token, issue_token
from app.security.audit import write_audit
from app.security.ratelimit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "ai_refresh"


async def _issue_and_send_verification(session: AsyncSession, user: User) -> None:
    """Создаёт verify-токен (в переданной сессии, без commit) и ставит письмо
    в arq-очередь. Commit — на стороне вызывающего (токен попадёт в БД одной
    транзакцией с регистрацией)."""
    from app.workers.redis_pool import get_pool

    settings = get_settings()
    raw = await issue_token(
        session, user.id, AuthTokenType.verify,
        timedelta(hours=settings.email_verify_ttl_hours),
    )
    url = f"{settings.app_base_url.rstrip('/')}/verify?token={raw}"
    pool = await get_pool()
    await pool.enqueue_job(
        "send_verification_email", to=user.email, user_name=user.full_name, verify_url=url
    )


async def _issue_and_send_reset(session: AsyncSession, user: User) -> None:
    """Создаёт reset-токен (без commit) и ставит письмо сброса пароля в очередь."""
    from app.workers.redis_pool import get_pool

    settings = get_settings()
    raw = await issue_token(
        session, user.id, AuthTokenType.reset,
        timedelta(hours=settings.email_reset_ttl_hours),
    )
    url = f"{settings.app_base_url.rstrip('/')}/reset-password?token={raw}"
    pool = await get_pool()
    await pool.enqueue_job(
        "send_password_reset_email", to=user.email, user_name=user.full_name, reset_url=url
    )


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, max_length=200)
    workspace_name: str | None = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: str | None = None
    role: UserRole
    tenant_id: str
    created_at: datetime


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    tenant: TenantOut


class RegisterResponse(BaseModel):
    """Ответ регистрации при Hard-confirm: access_token НЕ выдаётся,
    пользователю нужно подтвердить email из письма."""

    requires_verification: bool = True
    email: str


class VerifyIn(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class EmailIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=1, max_length=512)
    password: str = Field(min_length=8, max_length=200)


def _set_refresh_cookie(response: Response, token: str) -> None:
    from app.config import get_settings

    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        # Secure=True обязателен в production-HTTPS (cloudpub-туннель, прод-домен).
        # Управляется через REFRESH_COOKIE_SECURE — на локальном HTTP оставляем
        # False, чтобы браузер cookie вообще сохранил.
        secure=get_settings().refresh_cookie_secure,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    body: RegisterIn,
    session: AsyncSession = Depends(get_session),
) -> RegisterResponse:
    # Уникальность email — на уровне БД (unique-индекс).
    existing = await session.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    tenant = Tenant(
        id=f"tnt_{secrets.token_urlsafe(8).lower()}",
        name=body.workspace_name or (body.full_name or body.email.split("@")[0]) + " Workspace",
    )
    session.add(tenant)
    await session.flush()

    user = User(
        id=f"usr_{secrets.token_urlsafe(8).lower()}",
        tenant_id=tenant.id,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.admin,
        # email_verified_at=None — Hard-confirm: логин закрыт до подтверждения.
    )
    session.add(user)
    await session.flush()  # user должен существовать до вставки FK-токена
    # Verify-токен создаётся в той же транзакции, что и пользователь.
    await _issue_and_send_verification(session, user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    # access_token НЕ выдаём и refresh-cookie не ставим — сначала подтверждение.
    return RegisterResponse(requires_verification=True, email=user.email)


@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    body: LoginIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    result = await session.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        # Не раскрываем, что именно не так — стандартная мера.
        await write_audit(
            session,
            action="auth.login_failed",
            tenant_id=user.tenant_id if user else None,
            user_id=user.id if user else None,
            request=request,
            meta={"email": body.email.lower()},
        )
        await session.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Hard-confirm: вход закрыт, пока email не подтверждён. Код в detail —
    # чтобы фронт отличил эту ситуацию и предложил переслать письмо.
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="email_not_verified")

    tenant = await session.get(Tenant, user.tenant_id)
    access = create_access_token(user.id, user.tenant_id)
    refresh = create_refresh_token(user.id, user.tenant_id)
    _set_refresh_cookie(response, refresh)
    return AuthResponse(
        access_token=access,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    )


@router.post("/verify", response_model=AuthResponse)
@limiter.limit("10/minute")
async def verify(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    body: VerifyIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Подтверждает email по токену из письма и сразу авторизует пользователя
    (выдаёт access_token + refresh-cookie) — лишний логин после клика не нужен."""
    user_id = await consume_token(session, body.token, AuthTokenType.verify)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await write_audit(
        session, action="auth.email_verified",
        tenant_id=user.tenant_id, user_id=user.id, request=request,
    )
    await session.commit()

    tenant = await session.get(Tenant, user.tenant_id)
    access = create_access_token(user.id, user.tenant_id)
    refresh_token = create_refresh_token(user.id, user.tenant_id)
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(
        access_token=access,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    )


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("1/minute")
async def resend_verification(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    body: EmailIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Повторно шлёт письмо подтверждения. Ответ всегда одинаковый — не
    раскрываем, зарегистрирован ли адрес и подтверждён ли он."""
    result = await session.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is not None and user.email_verified_at is None:
        await _issue_and_send_verification(session, user)
        await session.commit()
    return {"status": "accepted"}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    body: EmailIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Шлёт письмо со ссылкой сброса пароля. Ответ всегда одинаковый, чтобы
    нельзя было перебором узнать, какие адреса зарегистрированы."""
    result = await session.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is not None:
        await _issue_and_send_reset(session, user)
        await session.commit()
    return {"status": "accepted"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def reset_password(
    request: Request,
    body: ResetIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Меняет пароль по reset-токену. Заодно подтверждает email (владение
    ящиком доказано) и чистит refresh-cookie в текущем браузере. NB: JWT
    stateless — refresh-токены, уже выданные на другие устройства, продолжат
    работать до истечения TTL (серверного denylist пока нет, см. TODO)."""
    user_id = await consume_token(session, body.token, AuthTokenType.reset)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user.password_hash = hash_password(body.password)
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await write_audit(
        session, action="auth.password_reset",
        tenant_id=user.tenant_id, user_id=user.id, request=request,
    )
    await session.commit()

    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = decode_token(token, "refresh")
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=f"Invalid refresh: {exc}") from exc

    user = await session.get(User, payload.get("sub"))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    tenant = await session.get(Tenant, user.tenant_id)

    new_access = create_access_token(user.id, user.tenant_id)
    new_refresh = create_refresh_token(user.id, user.tenant_id)
    _set_refresh_cookie(response, new_refresh)
    return AuthResponse(
        access_token=new_access,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AuthResponse)
async def me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    tenant = await session.get(Tenant, user.tenant_id)
    # Возвращаем тот же формат, что и login — без обновления токена.
    return AuthResponse(
        access_token="",  # /me не выдаёт новый access; используйте /refresh
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    )
