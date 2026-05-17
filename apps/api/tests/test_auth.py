"""Тесты регистрации/логина/refresh + изоляции tenant'ов."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def raw_client():
    """Чистый клиент без авто-регистрации (в отличие от стандартного `client`)."""
    from app.db.session import Base, engine
    from app.main import app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_register_creates_tenant_and_user(raw_client):
    resp = await raw_client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "topsecret-123",
            "workspace_name": "Acme",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["role"] == "admin"
    assert body["tenant"]["name"] == "Acme"
    assert "ai_refresh" in resp.cookies


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(raw_client):
    payload = {"email": "dup@example.com", "password": "topsecret-123"}
    first = await raw_client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = await raw_client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_returns_token(raw_client):
    await raw_client.post(
        "/api/v1/auth/register",
        json={"email": "bob@example.com", "password": "topsecret-123"},
    )
    resp = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "topsecret-123"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(raw_client):
    await raw_client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "topsecret-123"},
    )
    resp = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "wrong-password-xx"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_requires_token(raw_client):
    resp = await raw_client.get("/api/v1/integrations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation_for_integrations(raw_client):
    a = await raw_client.post(
        "/api/v1/auth/register",
        json={"email": "a@example.com", "password": "topsecret-123"},
    )
    b = await raw_client.post(
        "/api/v1/auth/register",
        json={"email": "b@example.com", "password": "topsecret-123"},
    )
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]

    # A создаёт интеграцию
    create = await raw_client.post(
        "/api/v1/integrations/bitrix24/webhook",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"label": "A's portal", "webhook_url": "https://a.bitrix24.ru/rest/1/abc/"},
    )
    assert create.status_code == 201
    integration_id = create.json()["id"]

    # A видит свою
    list_a = await raw_client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert len(list_a.json()) == 1

    # B не видит ничего
    list_b = await raw_client.get(
        "/api/v1/integrations",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_b.json() == []

    # B не может получить чужую интеграцию по id
    cross = await raw_client.get(
        f"/api/v1/integrations/{integration_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert cross.status_code == 404


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token(raw_client):
    reg = await raw_client.post(
        "/api/v1/auth/register",
        json={"email": "ref@example.com", "password": "topsecret-123"},
    )
    assert reg.status_code == 201
    # Cookie уже стоит в raw_client после register.
    resp = await raw_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_me_returns_current_user(raw_client):
    reg = await raw_client.post(
        "/api/v1/auth/register",
        json={"email": "me@example.com", "password": "topsecret-123"},
    )
    token = reg.json()["access_token"]
    resp = await raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "me@example.com"
