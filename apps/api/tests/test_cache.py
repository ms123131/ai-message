"""Тесты Redis-кэша дашборда."""

from __future__ import annotations

import pytest

from app.cache import cache_get, cache_set, make_cache_key


def test_cache_key_is_deterministic():
    """Один и тот же набор параметров → один и тот же ключ."""
    a = make_cache_key("overview", tenant_id="tnt_1", days=7, integration_id=None)
    b = make_cache_key("overview", tenant_id="tnt_1", days=7, integration_id=None)
    assert a == b


def test_cache_key_isolates_tenants():
    """Tenant — обязательная часть ключа: разные tenant'ы не должны
    видеть кэш друг друга (data leak)."""
    a = make_cache_key("overview", tenant_id="tnt_1", days=7)
    b = make_cache_key("overview", tenant_id="tnt_2", days=7)
    assert a != b


def test_cache_key_ignores_none_params():
    """None-параметры (фильтр не задан) не должны менять ключ."""
    a = make_cache_key("overview", tenant_id="t", days=7)
    b = make_cache_key("overview", tenant_id="t", days=7, integration_id=None)
    assert a == b


@pytest.mark.asyncio
async def test_cache_get_returns_none_when_redis_unavailable():
    """В тестовом окружении get_pool возвращает _FakeArqPool без .get,
    cache_get должен поймать исключение и тихо отдать None — иначе любой
    сбой Redis в проде ронял бы дашборд."""
    key = make_cache_key("overview", tenant_id="t", days=7)
    result = await cache_get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_set_does_not_raise_when_redis_unavailable():
    """Аналогично — cache_set silent-fails. Дашборд должен работать,
    даже если кэш-слой временно сломан."""
    key = make_cache_key("overview", tenant_id="t", days=7)
    # Не должно бросить
    await cache_set(key, {"x": 1, "y": [1, 2, 3]})


@pytest.mark.asyncio
async def test_overview_works_without_cache(client, auth_tenant_id):
    """Smoke: эндпоинт overview всё ещё работает с подключённой обёрткой
    кэша при недоступном Redis (silent fallback в cache_get)."""
    resp = await client.get("/api/v1/dashboard/overview?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "conversations" in body
    assert body["range_days"] == 7
