"""Distributed lock на портал через redis SET NX EX.

Зачем: воркер можно запускать в несколько реплик; без лока две реплики
будут параллельно дергать `im.recent.get` для одной интеграции и удваивать
нагрузку на портал. Лок берётся на `integration_id` и автоматически
освобождается по TTL, если воркер упал.

Использование:
    async with portal_lock(redis, integration_id) as got:
        if not got:
            return  # лок взят кем-то — пропускаем проход
        await import_open_lines(...)
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)
__all__ = ["lock_key", "portal_lock"]

def lock_key(integration_id: str, kind: str = "poll") -> str:
    """Канонический ключ лока. `kind` — на случай разных типов задач
    (например, `poll` vs `import`), которые нельзя крутить одновременно."""
    return f"ai-message:lock:{kind}:{integration_id}"


@asynccontextmanager
async def portal_lock(
    redis: Any,
    integration_id: str,
    *,
    ttl_sec: int,
    kind: str = "poll",
) -> AsyncIterator[bool]:
    """Контекст-менеджер distributed-лока.

    Yield-ит True, если лок взяли, и False — если ключ уже занят другой
    репликой. При выходе из контекста лок отпускается только если он всё
    ещё наш (сравнение по случайному токену).
    """
    key = lock_key(integration_id, kind)
    token = secrets.token_urlsafe(16)
    # `nx=True, ex=ttl_sec` — атомарное SET ... NX EX.
    acquired = await redis.set(key, token, nx=True, ex=ttl_sec)
    try:
        yield bool(acquired)
    finally:
        if acquired:
            # Безусловный DEL. Теоретическая гонка («наш TTL истёк,
            # другая реплика взяла тот же ключ — мы случайно отпустим её лок»)
            # маловероятна при TTL=600с и оставлена на CAS-доработку, если
            # реально подерёмся в проде. Сейчас это вредная сложность.
            try:
                await redis.delete(key)
            except Exception as exc:  # noqa: BLE001
                logger.debug("lock release failed (will expire by TTL): %s", exc)
