"""Тесты для Bitrix24 REST-клиента."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from app.db.models import Integration, IntegrationKind, IntegrationMode, IntegrationStatus
from app.db.session import AsyncSessionLocal, Base, engine
from app.integrations.bitrix24.client import (
    MAX_RPS,
    BitrixAPIError,
    BitrixClient,
    _PortalThrottle,
)


@pytest.fixture(autouse=True)
async def _setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    _PortalThrottle._locks.clear()
    _PortalThrottle._next_allowed.clear()
    yield


def _make_integration(**overrides) -> Integration:
    base = {
        "id": "intg_1",
        "kind": IntegrationKind.bitrix24,
        "mode": IntegrationMode.oauth,
        "label": "Test",
        "domain": "test.bitrix24.ru",
        "status": IntegrationStatus.connected,
        "client_id": "local.app",
        "client_secret": "secret",
        "access_token": "tok-access",
        "refresh_token": "tok-refresh",
        "member_id": "mem-1",
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    base.update(overrides)
    return Integration(**base)


def _ok(result):
    return httpx.Response(200, json={"result": result})


def _err(error: str, description: str | None = None):
    body = {"error": error}
    if description:
        body["error_description"] = description
    return httpx.Response(200, json=body)


async def _persist(integration: Integration):
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        await session.refresh(integration)
        return session


async def test_call_oauth_sends_auth_param():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _ok({"ID": 42})

    integration = _make_integration()
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            result = await client.call("crm.lead.get", {"id": 42})

    assert result == {"ID": 42}
    req = captured[0]
    assert str(req.url) == "https://test.bitrix24.ru/rest/crm.lead.get.json"
    body = parse_qs(req.content.decode())
    assert body["auth"] == ["tok-access"]
    assert body["id"] == ["42"]


async def test_call_raises_on_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return _err("ERROR_METHOD_NOT_FOUND", "Method not found")

    integration = _make_integration()
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            with pytest.raises(BitrixAPIError) as exc_info:
                await client.call("nope")
    assert exc_info.value.error == "ERROR_METHOD_NOT_FOUND"


async def test_expired_token_triggers_refresh_and_retry(monkeypatch):
    refresh_calls: list[dict] = []

    async def fake_refresh(*, client_id, client_secret, refresh_token_value):
        refresh_calls.append({"refresh_token_value": refresh_token_value})
        from app.integrations.bitrix24.oauth import TokenResponse

        return TokenResponse(
            access_token="new-access",
            refresh_token="new-refresh",
            expires_in=3600,
            member_id="mem-1",
            scope="crm",
        )

    monkeypatch.setattr(
        "app.integrations.bitrix24.client.refresh_token", fake_refresh
    )

    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        body = parse_qs(request.content.decode())
        if state["calls"] == 1:
            assert body["auth"] == ["tok-access"]
            return _err("expired_token")
        assert body["auth"] == ["new-access"]
        return _ok({"ok": True})

    integration = _make_integration()
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            result = await client.call("user.current")

    assert result == {"ok": True}
    assert len(refresh_calls) == 1
    assert integration.access_token == "new-access"
    assert integration.refresh_token == "new-refresh"


async def test_proactive_refresh_when_token_about_to_expire(monkeypatch):
    called = {"n": 0}

    async def fake_refresh(*, client_id, client_secret, refresh_token_value):
        called["n"] += 1
        from app.integrations.bitrix24.oauth import TokenResponse

        return TokenResponse(
            access_token="fresh",
            refresh_token="fresh-r",
            expires_in=3600,
        )

    monkeypatch.setattr(
        "app.integrations.bitrix24.client.refresh_token", fake_refresh
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = parse_qs(request.content.decode())
        assert body["auth"] == ["fresh"]
        return _ok([])

    # Токен истекает через 1 минуту — меньше REFRESH_LEEWAY (5 минут).
    integration = _make_integration(
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            await client.call("crm.lead.list")
    assert called["n"] == 1


async def test_webhook_mode_uses_webhook_url():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _ok([])

    integration = _make_integration(
        mode=IntegrationMode.webhook,
        webhook_url="https://test.bitrix24.ru/rest/1/abcdef",
        access_token=None,
        refresh_token=None,
        client_id=None,
        client_secret=None,
        expires_at=None,
    )
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            await client.call("crm.lead.list")

    req = captured[0]
    assert str(req.url) == "https://test.bitrix24.ru/rest/1/abcdef/crm.lead.list.json"
    body = parse_qs(req.content.decode())
    assert "auth" not in body


async def test_batch_packs_commands():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _ok(
            {
                "result": {"a": {"ID": 1}, "b": {"ID": 2}},
                "result_error": [],
                "result_total": [],
                "result_next": [],
                "result_time": [],
            }
        )

    integration = _make_integration()
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            result = await client.batch(
                {"a": "crm.lead.get?id=1", "b": "crm.lead.get?id=2"}
            )

    assert result == {"a": {"ID": 1}, "b": {"ID": 2}}
    body = parse_qs(captured[0].content.decode())
    assert body["cmd[a]"] == ["crm.lead.get?id=1"]
    assert body["cmd[b]"] == ["crm.lead.get?id=2"]
    assert body["halt"] == ["0"]


async def test_batch_size_limit():
    integration = _make_integration()
    transport = httpx.MockTransport(lambda r: _ok({}))
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            commands = {f"k{i}": "user.current" for i in range(51)}
            with pytest.raises(ValueError):
                await client.batch(commands)


async def test_throttle_enforces_min_interval():
    import asyncio

    timestamps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        loop = asyncio.get_running_loop()
        timestamps.append(loop.time())
        return _ok(None)

    integration = _make_integration()
    transport = httpx.MockTransport(handler)
    async with AsyncSessionLocal() as session:
        session.add(integration)
        await session.commit()
        async with BitrixClient(integration, session, transport=transport) as client:
            await asyncio.gather(
                client.call("user.current"),
                client.call("user.current"),
                client.call("user.current"),
            )

    # Между запросами должно быть не меньше 1/MAX_RPS секунд
    min_interval = 1.0 / MAX_RPS
    deltas = [b - a for a, b in zip(timestamps, timestamps[1:], strict=False)]
    for d in deltas:
        assert d >= min_interval - 0.05  # допуск на джиттер event loop


# silence unused-import warning in some lint configs
_ = json
