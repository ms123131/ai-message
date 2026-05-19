"""Тесты distributed-лока на fakeredis."""

from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from app.workers.locks import lock_key, portal_lock


@pytest.mark.asyncio
async def test_lock_acquires_and_releases():
    redis = FakeRedis()
    try:
        async with portal_lock(redis, "intg1", ttl_sec=60) as got:
            assert got is True
            # Под локом ключ существует.
            assert await redis.get(lock_key("intg1")) is not None
        # После выхода ключ удалён.
        assert await redis.get(lock_key("intg1")) is None
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_lock_blocks_second_acquire():
    redis = FakeRedis()
    try:
        async with portal_lock(redis, "intg2", ttl_sec=60) as first:
            assert first is True
            # Параллельная попытка взять тот же лок — не должна получить.
            async with portal_lock(redis, "intg2", ttl_sec=60) as second:
                assert second is False
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_lock_independent_per_integration():
    redis = FakeRedis()
    try:
        async with portal_lock(redis, "intg-a", ttl_sec=60) as a:
            async with portal_lock(redis, "intg-b", ttl_sec=60) as b:
                # Разные ключи — оба берутся.
                assert a is True
                assert b is True
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_lock_kinds_are_isolated():
    redis = FakeRedis()
    try:
        async with portal_lock(redis, "intg3", ttl_sec=60, kind="poll") as a:
            async with portal_lock(
                redis, "intg3", ttl_sec=60, kind="import"
            ) as b:
                assert a is True
                assert b is True
    finally:
        await redis.aclose()
