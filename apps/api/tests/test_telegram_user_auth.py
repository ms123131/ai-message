"""QR-логин personal Telegram — без сетевого Telethon.

Мокаем `start_qr_session`/`poll_qr_session`/`confirm_password`/
`take_session_blob`/`teardown_qr_session` напрямую в модуле API-роутера.
Реальный Telethon не нужен: тесты проверяют контракт endpoint'ов и
маппинг состояний → БД.
"""

from __future__ import annotations

import pytest

from app.db.models import IntegrationKind, IntegrationStatus


@pytest.fixture
def _patch_qr(monkeypatch):
    """Управляемые заглушки qr-функций. Возвращает контейнер с настройками."""

    state = {
        "start_payload": {"qr_url": "tg://login?token=AAA", "expires_in": 300},
        "poll_payload": {
            "state": "waiting",
            "qr_url": "tg://login?token=BBB",
            "expires_in": 300,
        },
        "session_blob": "STRING_SESSION_FAKE",
        "me": {
            "id": "424242",
            "first_name": "Иван",
            "last_name": "Тестов",
            "username": "ivantestov",
            "phone": "79991234567",
        },
        "raise_unconfigured": False,
    }

    async def fake_start(integration_id):
        if state["raise_unconfigured"]:
            from app.integrations.telegram_user import TelegramNotConfigured

            raise TelegramNotConfigured("telethon missing")
        return state["start_payload"]

    async def fake_poll(integration_id):
        return state["poll_payload"]

    async def fake_password(integration_id, password):
        return {"state": "connected"}

    async def fake_take(integration_id):
        return state["session_blob"], state["me"]

    async def fake_teardown(integration_id):
        return None

    target = "app.api.v1.integrations_telegram_user"
    monkeypatch.setattr(f"{target}.start_qr_session", fake_start)
    monkeypatch.setattr(f"{target}.poll_qr_session", fake_poll)
    monkeypatch.setattr(f"{target}.confirm_password", fake_password)
    monkeypatch.setattr(f"{target}.take_session_blob", fake_take)
    monkeypatch.setattr(f"{target}.teardown_qr_session", fake_teardown)

    return state


@pytest.mark.asyncio
async def test_qr_start_creates_pending_integration(client, _patch_qr):
    resp = await client.post("/api/v1/integrations/telegram-user/qr/start")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["qr_url"] == "tg://login?token=AAA"
    assert body["expires_in"] == 300
    integration_id = body["integration_id"]

    lst = (await client.get("/api/v1/integrations")).json()
    me = next(i for i in lst if i["id"] == integration_id)
    assert me["kind"] == IntegrationKind.telegram_user.value
    assert me["status"] == IntegrationStatus.pending.value


@pytest.mark.asyncio
async def test_qr_poll_waiting_returns_refreshed_url(client, _patch_qr):
    start = (
        await client.post("/api/v1/integrations/telegram-user/qr/start")
    ).json()
    iid = start["integration_id"]

    resp = await client.post(
        f"/api/v1/integrations/telegram-user/{iid}/qr/poll"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "waiting"
    assert body["qr_url"] == "tg://login?token=BBB"
    assert body["integration"] is None


@pytest.mark.asyncio
async def test_qr_poll_requires_password(client, _patch_qr):
    _patch_qr["poll_payload"] = {"state": "requires_password"}
    start = (
        await client.post("/api/v1/integrations/telegram-user/qr/start")
    ).json()
    iid = start["integration_id"]

    resp = await client.post(
        f"/api/v1/integrations/telegram-user/{iid}/qr/poll"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "requires_password"
    assert body["integration"] is None


@pytest.mark.asyncio
async def test_qr_poll_connected_persists_session(client, _patch_qr):
    """Успешный poll должен переключить integration в connected,
    обновить label/domain/member_id и больше не светить auth_blob наружу.
    """
    _patch_qr["poll_payload"] = {"state": "connected"}
    start = (
        await client.post("/api/v1/integrations/telegram-user/qr/start")
    ).json()
    iid = start["integration_id"]

    resp = await client.post(
        f"/api/v1/integrations/telegram-user/{iid}/qr/poll"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "connected"
    assert body["integration"] is not None
    out = body["integration"]
    assert out["id"] == iid
    assert out["status"] == IntegrationStatus.connected.value
    assert out["member_id"] == "424242"
    assert out["label"] == "Иван Тестов"
    assert out["domain"] == "+79991234567"
    # auth_blob не должен светиться в schema
    assert "auth_blob" not in out


@pytest.mark.asyncio
async def test_password_completes_2fa(client, _patch_qr):
    _patch_qr["poll_payload"] = {"state": "requires_password"}
    start = (
        await client.post("/api/v1/integrations/telegram-user/qr/start")
    ).json()
    iid = start["integration_id"]

    # сначала poll — попали в 2FA
    poll = await client.post(
        f"/api/v1/integrations/telegram-user/{iid}/qr/poll"
    )
    assert poll.json()["state"] == "requires_password"

    # вводим пароль
    resp = await client.post(
        f"/api/v1/integrations/telegram-user/{iid}/password",
        json={"password": "hunter2"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "connected"
    assert resp.json()["integration"]["status"] == (
        IntegrationStatus.connected.value
    )


@pytest.mark.asyncio
async def test_qr_start_503_when_not_configured(client, _patch_qr):
    """Без API_ID/API_HASH endpoint должен отвечать 503, а не падать."""
    _patch_qr["raise_unconfigured"] = True
    resp = await client.post("/api/v1/integrations/telegram-user/qr/start")
    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"]["code"] == "telegram_not_configured"

    # и не должно остаться pending-черновика
    lst = (await client.get("/api/v1/integrations")).json()
    assert all(
        i["kind"] != IntegrationKind.telegram_user.value for i in lst
    )


@pytest.mark.asyncio
async def test_poll_404_for_other_tenant_integration(client, _patch_qr):
    """Чужую интеграцию не видим — 404."""
    resp = await client.post(
        "/api/v1/integrations/telegram-user/nonexistent/qr/poll"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_qr_session_expired_returns_410(client, _patch_qr, monkeypatch):
    from app.integrations.telegram_user import QRSessionExpired

    async def expired(integration_id):
        raise QRSessionExpired(integration_id)

    start = (
        await client.post("/api/v1/integrations/telegram-user/qr/start")
    ).json()
    iid = start["integration_id"]

    monkeypatch.setattr(
        "app.api.v1.integrations_telegram_user.poll_qr_session", expired
    )
    resp = await client.post(
        f"/api/v1/integrations/telegram-user/{iid}/qr/poll"
    )
    assert resp.status_code == 410
    assert resp.json()["detail"]["code"] == "qr_session_expired"
