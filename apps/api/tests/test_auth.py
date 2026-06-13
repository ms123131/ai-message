"""Тесты регистрации/логина/refresh + подтверждения email + сброса пароля."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

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


def _link_token(pool, job_name: str, url_key: str) -> str:
    """Достаёт токен из ссылки в последнем письме, поставленном в fake-очередь."""
    for name, _args, kwargs in reversed(pool.enqueued):
        if name == job_name:
            url = kwargs[url_key]
            return parse_qs(urlparse(url).query)["token"][0]
    raise AssertionError(f"письмо {job_name} не поставлено в очередь")


async def _register(raw_client, email: str, password: str = "topsecret-123", **extra):
    resp = await raw_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, **extra},
    )
    return resp


async def _register_verified_token(raw_client, pool, email, password="topsecret-123") -> str:
    """Регистрирует, подтверждает email через verify-токен из письма и
    возвращает access_token."""
    reg = await _register(raw_client, email, password)
    assert reg.status_code == 201, reg.text
    token = _link_token(pool, "send_verification_email", "verify_url")
    verify = await raw_client.post("/api/v1/auth/verify", json={"token": token})
    assert verify.status_code == 200, verify.text
    return verify.json()["access_token"]


@pytest.mark.asyncio
async def test_register_requires_verification_and_issues_no_token(raw_client):
    resp = await _register(raw_client, "alice@example.com", workspace_name="Acme")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    # Hard-confirm: ни токена, ни refresh-cookie, только флаг.
    assert body == {"requires_verification": True, "email": "alice@example.com"}
    assert "access_token" not in body
    assert "ai_refresh" not in resp.cookies


@pytest.mark.asyncio
async def test_register_enqueues_verification_email(raw_client, _stub_arq_pool):
    await _register(raw_client, "newby@example.com")
    sent = [j for j in _stub_arq_pool.enqueued if j[0] == "send_verification_email"]
    assert len(sent) == 1
    assert sent[0][2]["to"] == "newby@example.com"
    assert "/verify?token=" in sent[0][2]["verify_url"]


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(raw_client):
    first = await _register(raw_client, "dup@example.com")
    assert first.status_code == 201
    second = await _register(raw_client, "dup@example.com")
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_blocked_until_verified(raw_client):
    await _register(raw_client, "unv@example.com")
    resp = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "unv@example.com", "password": "topsecret-123"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "email_not_verified"


@pytest.mark.asyncio
async def test_verify_then_login_works(raw_client, _stub_arq_pool):
    await _register_verified_token(raw_client, _stub_arq_pool, "bob@example.com")
    resp = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "bob@example.com", "password": "topsecret-123"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_verify_returns_token_and_cookie(raw_client, _stub_arq_pool):
    token = await _register_verified_token(raw_client, _stub_arq_pool, "v@example.com")
    assert token  # verify сразу авторизует
    # refresh-cookie выставлен — /refresh должен работать.
    refreshed = await raw_client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text


@pytest.mark.asyncio
async def test_verify_rejects_bad_token(raw_client):
    resp = await raw_client.post("/api/v1/auth/verify", json={"token": "garbage"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_token_single_use(raw_client, _stub_arq_pool):
    await _register(raw_client, "once@example.com")
    token = _link_token(_stub_arq_pool, "send_verification_email", "verify_url")
    first = await raw_client.post("/api/v1/auth/verify", json={"token": token})
    assert first.status_code == 200
    second = await raw_client.post("/api/v1/auth/verify", json={"token": token})
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_resend_verification_is_generic(raw_client, _stub_arq_pool):
    await _register(raw_client, "re@example.com")
    _stub_arq_pool.enqueued.clear()
    resp = await raw_client.post(
        "/api/v1/auth/resend-verification", json={"email": "re@example.com"}
    )
    assert resp.status_code == 202
    sent = [j for j in _stub_arq_pool.enqueued if j[0] == "send_verification_email"]
    assert len(sent) == 1
    # Для несуществующего адреса — тот же ответ, но письма нет.
    # resend лимитирован 1/мин — сбрасываем лимитер, чтобы проверить вторую ветку.
    from app.security.ratelimit import limiter

    limiter.reset()
    _stub_arq_pool.enqueued.clear()
    unknown = await raw_client.post(
        "/api/v1/auth/resend-verification", json={"email": "nobody@example.com"}
    )
    assert unknown.status_code == 202
    assert not [j for j in _stub_arq_pool.enqueued if j[0] == "send_verification_email"]


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(raw_client):
    await _register(raw_client, "carol@example.com")
    resp = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "carol@example.com", "password": "wrong-password-xx"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_forgot_password_is_generic(raw_client, _stub_arq_pool):
    await _register(raw_client, "fp@example.com")
    _stub_arq_pool.enqueued.clear()
    known = await raw_client.post(
        "/api/v1/auth/forgot-password", json={"email": "fp@example.com"}
    )
    assert known.status_code == 202
    assert [j for j in _stub_arq_pool.enqueued if j[0] == "send_password_reset_email"]

    _stub_arq_pool.enqueued.clear()
    unknown = await raw_client.post(
        "/api/v1/auth/forgot-password", json={"email": "ghost@example.com"}
    )
    assert unknown.status_code == 202
    assert not [j for j in _stub_arq_pool.enqueued if j[0] == "send_password_reset_email"]


@pytest.mark.asyncio
async def test_reset_password_flow(raw_client, _stub_arq_pool):
    await _register_verified_token(raw_client, _stub_arq_pool, "rp@example.com")
    await raw_client.post("/api/v1/auth/forgot-password", json={"email": "rp@example.com"})
    token = _link_token(_stub_arq_pool, "send_password_reset_email", "reset_url")

    reset = await raw_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "password": "brand-new-pass-9"},
    )
    assert reset.status_code == 204

    # Старый пароль больше не работает, новый — работает.
    old = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "rp@example.com", "password": "topsecret-123"},
    )
    assert old.status_code == 401
    new = await raw_client.post(
        "/api/v1/auth/login",
        json={"email": "rp@example.com", "password": "brand-new-pass-9"},
    )
    assert new.status_code == 200, new.text


@pytest.mark.asyncio
async def test_reset_token_single_use(raw_client, _stub_arq_pool):
    await _register_verified_token(raw_client, _stub_arq_pool, "ru@example.com")
    await raw_client.post("/api/v1/auth/forgot-password", json={"email": "ru@example.com"})
    token = _link_token(_stub_arq_pool, "send_password_reset_email", "reset_url")
    first = await raw_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "another-pass-1"}
    )
    assert first.status_code == 204
    second = await raw_client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "another-pass-2"}
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_protected_endpoint_requires_token(raw_client):
    resp = await raw_client.get("/api/v1/integrations")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tenant_isolation_for_integrations(raw_client, _stub_arq_pool):
    token_a = await _register_verified_token(raw_client, _stub_arq_pool, "a@example.com")
    token_b = await _register_verified_token(raw_client, _stub_arq_pool, "b@example.com")

    # A: сидируем pending-интеграцию и забираем её через /connect.
    from app.db.models import (
        Integration,
        IntegrationKind,
        IntegrationMode,
        IntegrationStatus,
    )
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id="b24_a",
                tenant_id=None,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="A portal",
                domain="a.bitrix24.ru",
                status=IntegrationStatus.connected,
                access_token="x",
                refresh_token="y",
            )
        )
        await session.commit()

    claim = await raw_client.post(
        "/api/v1/integrations/bitrix24/connect",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"domain": "a.bitrix24.ru"},
    )
    assert claim.status_code == 200
    integration_id = claim.json()["id"]

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
async def test_refresh_returns_new_access_token(raw_client, _stub_arq_pool):
    # Cookie ставится на verify — берём её через полный цикл.
    await _register_verified_token(raw_client, _stub_arq_pool, "ref@example.com")
    resp = await raw_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_me_returns_current_user(raw_client, _stub_arq_pool):
    token = await _register_verified_token(raw_client, _stub_arq_pool, "me@example.com")
    resp = await raw_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "me@example.com"
