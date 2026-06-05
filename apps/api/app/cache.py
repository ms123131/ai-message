"""Лёгкий Redis-кэш для аналитических эндпоинтов (фаза 7 — оптимизация).

Применяется к дашборду: `/dashboard/*` считают агрегаты на лету, что на
больших порталах даёт latency 0.5-2с на запрос. Поскольку оператор
обновляет страницу каждые ~60с, кэш на 30-60с снимает значительную
часть нагрузки без видимой потери актуальности.

Дизайн:
- ключ кэша — `dashv1:<tenant_id>:<endpoint>:<sha256(json_args)>`.
  Tenant-isolated, endpoint-prefixed (легко инвалидировать целый домен
  через `SCAN+DEL` или `FLUSHDB` на staging).
- значение — JSON (`json.dumps(..., default=str)`, чтобы datetime
  сериализовался в ISO-строку без боли).
- TTL берётся из настроек (`dashboard_cache_ttl_sec`, по умолчанию 60с);
  0 = кэш отключён, удобно в тестах.
- провал в Redis (`RedisError`) — silent fallback: считаем как кэш-мисс
  и идём в БД. Не падаем — дашборд должен работать даже при недоступном
  Redis.

Использование:

    @router.get("/overview")
    async def overview(...):
        cache_key = make_cache_key("overview", tenant_id=user.tenant_id, days=days)
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached
        data = ...  # тяжёлый запрос
        await cache_set(cache_key, data)
        return data
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.config import get_settings
from app.workers.redis_pool import get_pool

logger = logging.getLogger(__name__)

_KEY_VERSION = "dashv1"


def make_cache_key(endpoint: str, *, tenant_id: str, **params: Any) -> str:
    """Стабильный ключ из имени эндпоинта + tenant + произвольных параметров.
    None-значения отбрасываются — это нормальная семантика «параметр не задан»."""
    payload = {k: v for k, v in params.items() if v is not None}
    canonical = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{_KEY_VERSION}:{tenant_id}:{endpoint}:{digest}"


async def cache_get(key: str) -> Any | None:
    settings = get_settings()
    if settings.dashboard_cache_ttl_sec <= 0:
        return None
    try:
        pool = await get_pool()
        raw = await pool.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache_get failed key=%s err=%s", key, exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        # Старая запись несовместимого формата — игнорируем.
        return None


async def cache_set(key: str, value: Any) -> None:
    settings = get_settings()
    ttl = settings.dashboard_cache_ttl_sec
    if ttl <= 0:
        return
    try:
        pool = await get_pool()
        payload = json.dumps(value, default=str)
        await pool.set(key, payload, ex=ttl)
    except Exception as exc:  # noqa: BLE001
        logger.debug("cache_set failed key=%s err=%s", key, exc)


async def cache_invalidate_tenant(tenant_id: str) -> int:
    """Удаляет все ключи кэша для указанного tenant'а.

    Вызывается из импортера/webhook'а после новых данных, если нужно
    мгновенное обновление дашборда без ожидания TTL. По умолчанию НЕ
    используется — полагаемся на TTL. Возвращает число удалённых ключей.
    """
    pattern = f"{_KEY_VERSION}:{tenant_id}:*"
    try:
        pool = await get_pool()
        deleted = 0
        async for key in pool.scan_iter(match=pattern, count=200):
            await pool.delete(key)
            deleted += 1
        return deleted
    except Exception as exc:  # noqa: BLE001
        logger.warning("cache_invalidate failed pattern=%s err=%s", pattern, exc)
        return 0


__all__ = [
    "cache_get",
    "cache_invalidate_tenant",
    "cache_set",
    "make_cache_key",
]
