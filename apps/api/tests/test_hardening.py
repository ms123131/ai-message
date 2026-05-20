"""Тесты production-hardening: rate limit и audit log."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import AuditLog
from app.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_login_rate_limit_triggers_429(client):
    # Лимит login — 10/minute. 11-й запрос должен получить 429.
    for _ in range(10):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        # 401 — нет такого пользователя; rate-лимит ещё не сработал
        assert resp.status_code in (401, 429)

    final = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "wrong"},
    )
    assert final.status_code == 429
    assert "Too many requests" in final.json()["detail"]


@pytest.mark.asyncio
async def test_audit_log_records_failed_login(client):
    # Используем уникальный email, чтобы не путаться с другими тестами.
    await client.post(
        "/api/v1/auth/login",
        json={"email": "audit-victim@example.com", "password": "wrong"},
    )

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "auth.login_failed")
            )
        ).scalars().all()
        emails = [r.meta.get("email") for r in rows if r.meta]
        assert "audit-victim@example.com" in emails


@pytest.mark.asyncio
async def test_audit_log_records_integration_delete(client, auth_tenant_id):
    """Удаление интеграции пишет в audit_logs."""
    import secrets

    from app.db.models import (
        Integration,
        IntegrationKind,
        IntegrationMode,
        IntegrationStatus,
    )

    integration_id = f"b24_{secrets.token_urlsafe(8).lower()}"
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=auth_tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="audit-test",
                domain="audit.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        await session.commit()

    resp = await client.delete(f"/api/v1/integrations/{integration_id}")
    assert resp.status_code == 204

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.action == "integration.delete",
                    AuditLog.target_id == integration_id,
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == auth_tenant_id
        assert rows[0].meta["domain"] == "audit.bitrix24.ru"
