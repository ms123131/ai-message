"""Helpers для записи audit log."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request: Request | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """Создаёт запись AuditLog в текущей сессии (без коммита).

    Коммит ожидается от вызывающего кода — обычно audit пишется в той же
    транзакции, что и основное действие, чтобы не получить запись без
    реального эффекта (или наоборот).
    """
    entry = AuditLog(
        id=f"adt_{secrets.token_urlsafe(8).lower()}",
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip=_client_ip(request),
        meta=meta,
    )
    session.add(entry)
