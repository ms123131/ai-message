"""Тесты /install/bitrix24 — приём токенов от Bitrix24."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import Integration, IntegrationStatus
from app.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_install_creates_pending_integration(client):
    resp = await client.post(
        "/api/v1/install/bitrix24",
        data={
            "AUTH_ID": "access-from-b24",
            "REFRESH_ID": "refresh-from-b24",
            "AUTH_EXPIRES": "3600",
            "DOMAIN": "acme.bitrix24.ru",
            "member_id": "abc123",
            "APP_SID": "sid",
            "PROTOCOL": "1",
            "LANG": "ru",
        },
    )
    assert resp.status_code == 200
    assert "installFinish" in resp.text
    # X-Frame-Options должен быть ALLOWALL — страница открывается в iframe.
    assert resp.headers["x-frame-options"].lower() == "allowall"

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Integration))).scalars().all()
        assert len(rows) == 1
        intg = rows[0]
        assert intg.tenant_id is None  # pending, ждёт /connect
        assert intg.domain == "acme.bitrix24.ru"
        assert intg.member_id == "abc123"
        assert intg.access_token == "access-from-b24"
        assert intg.refresh_token == "refresh-from-b24"
        assert intg.status == IntegrationStatus.connected


@pytest.mark.asyncio
async def test_install_updates_existing_integration_tokens(client):
    """Если приложение переустанавливают — обновляем токены, не плодим записи."""
    from app.db.models import Tenant

    async with AsyncSessionLocal() as session:
        session.add(Tenant(id="tnt_x", name="X"))
        await session.flush()
        session.add(
            Integration(
                id="b24_old",
                tenant_id="tnt_x",
                kind="bitrix24",  # type: ignore[arg-type]
                mode="oauth",  # type: ignore[arg-type]
                label="Old",
                domain="acme.bitrix24.ru",
                status=IntegrationStatus.connected,
                access_token="old-access",
                refresh_token="old-refresh",
                member_id="abc123",
            )
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/install/bitrix24",
        data={
            "AUTH_ID": "new-access",
            "REFRESH_ID": "new-refresh",
            "AUTH_EXPIRES": "3600",
            "DOMAIN": "acme.bitrix24.ru",
            "member_id": "abc123",
        },
    )
    assert resp.status_code == 200

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(Integration))).scalars().all()
        assert len(rows) == 1
        intg = rows[0]
        assert intg.id == "b24_old"  # та же запись
        assert intg.tenant_id == "tnt_x"  # tenant сохранён
        assert intg.access_token == "new-access"
        assert intg.refresh_token == "new-refresh"


@pytest.mark.asyncio
async def test_install_get_returns_html(client):
    resp = await client.get("/api/v1/install/bitrix24")
    assert resp.status_code == 200
    assert "installFinish" in resp.text
