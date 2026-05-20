"""Auth endpoints: register, login, refresh, logout, me."""

from __future__ import annotations

import secrets
from datetime import datetime

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
from app.db import get_session
from app.db.models import Tenant, User, UserRole
from app.security.audit import write_audit
from app.security.ratelimit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "ai_refresh"


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


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=int(REFRESH_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=False,  # TODO: True в production за HTTPS
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/api/v1/auth")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    body: RegisterIn,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
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
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    await session.refresh(user)
    await session.refresh(tenant)

    access = create_access_token(user.id, tenant.id)
    refresh = create_refresh_token(user.id, tenant.id)
    _set_refresh_cookie(response, refresh)
    return AuthResponse(
        access_token=access,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    )


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

    tenant = await session.get(Tenant, user.tenant_id)
    access = create_access_token(user.id, user.tenant_id)
    refresh = create_refresh_token(user.id, user.tenant_id)
    _set_refresh_cookie(response, refresh)
    return AuthResponse(
        access_token=access,
        user=UserOut.model_validate(user),
        tenant=TenantOut.model_validate(tenant),
    )


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
