"""JWT + password hashing для аутентификации."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()

JWT_ALGO = "HS256"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False


def _encode(payload: dict[str, Any], ttl: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    full = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(full, settings.jwt_secret, algorithm=JWT_ALGO)


def create_access_token(user_id: str, tenant_id: str) -> str:
    return _encode({"sub": user_id, "tid": tenant_id, "typ": "access"}, ACCESS_TTL)


def create_refresh_token(user_id: str, tenant_id: str) -> str:
    return _encode({"sub": user_id, "tid": tenant_id, "typ": "refresh"}, REFRESH_TTL)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Возвращает payload или бросает jwt.PyJWTError / ValueError."""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGO])
    if payload.get("typ") != expected_type:
        raise ValueError(f"unexpected token type: {payload.get('typ')}")
    return payload
