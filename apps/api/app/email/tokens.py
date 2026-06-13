"""Одноразовые токены для подтверждения email и сброса пароля.

В БД храним только sha256-хэш токена — сырой токен живёт лишь в ссылке
письма. При погашении проставляется used_at, повторно токен не действует.
Коммит транзакции — на стороне вызывающего (issue_token/consume_token
работают в рамках переданной сессии).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthToken, AuthTokenType


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def issue_token(
    session: AsyncSession,
    user_id: str,
    token_type: AuthTokenType,
    ttl: timedelta,
) -> str:
    """Создаёт токен в сессии (без commit) и возвращает СЫРОЙ токен для письма."""
    raw = secrets.token_urlsafe(32)
    token = AuthToken(
        id=f"avt_{secrets.token_urlsafe(8).lower()}",
        user_id=user_id,
        token_hash=_hash(raw),
        type=token_type,
        expires_at=datetime.now(UTC) + ttl,
    )
    session.add(token)
    return raw


async def consume_token(
    session: AsyncSession,
    raw: str,
    token_type: AuthTokenType,
) -> str | None:
    """Гасит токен. Возвращает user_id при успехе, иначе None.

    None означает: токен не найден / не того типа / уже использован /
    просрочен. Вызывающий сам решает, какую ошибку отдать.
    """
    result = await session.execute(
        select(AuthToken).where(
            AuthToken.token_hash == _hash(raw),
            AuthToken.type == token_type,
        )
    )
    token = result.scalar_one_or_none()
    if token is None or token.used_at is not None:
        return None

    expires_at = token.expires_at
    # На SQLite timestamptz может вернуться naive — нормализуем к UTC.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return None

    token.used_at = datetime.now(UTC)
    return token.user_id
