"""Тесты CRUD интеграций и connect-flow."""

from __future__ import annotations

import pytest

from app.db.models import (
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
)
from app.db.session import AsyncSessionLocal


async def _seed_pending_integration(domain: str = "acme.bitrix24.ru") -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="b24_pending_1",
            tenant_id=None,  # «осиротевшая» — ждёт привязки через /connect
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label=domain,
            domain=domain,
            status=IntegrationStatus.connected,
            access_token="access-xyz",
            refresh_token="refresh-xyz",
            member_id="member-abc",
        )
        session.add(integration)
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_list_integrations_empty_for_new_user(client):
    resp = await client.get("/api/v1/integrations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_connect_claims_pending_integration(client, auth_tenant_id):
    await _seed_pending_integration("acme.bitrix24.ru")
    resp = await client.post(
        "/api/v1/integrations/bitrix24/connect",
        json={"domain": "https://ACME.bitrix24.ru/", "label": "Acme prod"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["domain"] == "acme.bitrix24.ru"
    assert body["label"] == "Acme prod"
    assert body["status"] == "connected"

    list_resp = await client.get("/api/v1/integrations")
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["id"] == "b24_pending_1"


@pytest.mark.asyncio
async def test_connect_returns_not_installed_when_no_record(client):
    resp = await client.post(
        "/api/v1/integrations/bitrix24/connect",
        json={"domain": "missing.bitrix24.ru"},
    )
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["status"] == "not_installed"
    assert detail["domain"] == "missing.bitrix24.ru"
    assert "install_instructions_url" in detail


@pytest.mark.asyncio
async def test_connect_rejects_already_claimed_by_other_tenant(client):
    """Если портал уже привязан к другому tenant — отдаём 409."""
    from app.db.models import Tenant

    async with AsyncSessionLocal() as session:
        session.add(Tenant(id="tnt_someone_else", name="Other"))
        await session.flush()
        session.add(
            Integration(
                id="b24_owned",
                tenant_id="tnt_someone_else",
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Owned",
                domain="owned.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/integrations/bitrix24/connect",
        json={"domain": "owned.bitrix24.ru"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_delete_integration_works(client, auth_tenant_id):
    integration_id = await _seed_pending_integration()
    # Сначала «забираем» интеграцию.
    claim = await client.post(
        "/api/v1/integrations/bitrix24/connect",
        json={"domain": "acme.bitrix24.ru"},
    )
    assert claim.status_code == 200

    del_resp = await client.delete(f"/api/v1/integrations/{integration_id}")
    assert del_resp.status_code == 204

    assert (await client.get("/api/v1/integrations")).json() == []


@pytest.mark.asyncio
async def test_connect_requires_auth():
    """Без токена /connect должен возвращать 401."""
    from httpx import ASGITransport, AsyncClient

    from app.db.session import Base, engine
    from app.main import app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/integrations/bitrix24/connect",
            json={"domain": "x.bitrix24.ru"},
        )
        assert resp.status_code == 401
