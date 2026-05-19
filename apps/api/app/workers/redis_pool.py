"""Единая точка получения arq-пула Redis.

API-процесс использует пул, чтобы enqueue-ить задачи. Воркер свой пул
получает через `WorkerSettings.redis_settings`. В тестах фабрика подменяется
на fakeredis через monkeypatch.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings


def _redis_settings_from_url(url: str) -> RedisSettings:
    """arq.RedisSettings ожидает разобранные параметры, а не URL."""
    parsed = urlparse(url)
    db = 0
    if parsed.path and parsed.path != "/":
        try:
            db = int(parsed.path.lstrip("/"))
        except ValueError:
            db = 0
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=db,
        password=parsed.password,
        username=parsed.username,
    )


def redis_settings() -> RedisSettings:
    return _redis_settings_from_url(get_settings().redis_url)


# Кэш одного пула на процесс — пересоздавать на каждый запрос дорого
# (открывает соединения и устанавливает таймауты).
_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    """Возвращает (создавая при первом обращении) arq-пул для enqueue-ов."""
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_pool() -> None:
    """Закрывает пул при shutdown FastAPI."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def _set_pool_for_tests(pool: Any) -> None:
    """Только для тестов: подсадить заранее созданный пул (fakeredis)."""
    global _pool
    _pool = pool
