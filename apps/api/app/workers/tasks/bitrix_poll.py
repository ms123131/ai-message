"""Задачи поллинга Bitrix24 Open Channels.

`dispatch_poll` — диспетчер: раз в `bitrix24_poll_interval_sec` собирает
список подключённых интеграций, для каждой enqueue-ит `poll_integration`,
затем перевзводит сам себя через `_defer_by` (self-rescheduling pattern,
рекомендованный arq для произвольных интервалов).

`poll_integration` — один проход для одной интеграции под distributed-локом.
Под локом: импорт сообщений + ленивая суточная синхронизация PortalUser.
Если лок не взят (работает другая реплика) — корректно скипаем.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Integration, IntegrationMode, IntegrationStatus
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.importer import import_open_lines
from app.integrations.bitrix24.users_sync import sync_portal_users_if_stale
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)


async def dispatch_poll(ctx: dict[str, Any]) -> int:
    """Собирает список интеграций, ставит per-integration задачи, перевзводит
    сам себя.

    Возвращает число поставленных задач — попадает в arq job result, удобно
    смотреть в логах. Если интервал поллинга 0 — диспетчер останавливается
    (используется для дев-режима без B24).
    """
    settings = get_settings()
    interval = settings.bitrix24_poll_interval_sec
    if interval <= 0:
        logger.info("bitrix24 poll disabled (interval=0)")
        return 0

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Integration.id).where(
                Integration.mode == IntegrationMode.oauth,
                Integration.status == IntegrationStatus.connected,
                Integration.tenant_id.is_not(None),
            )
        )
        ids = [r[0] for r in rows.all()]

    pool = ctx["redis"]
    for integration_id in ids:
        await pool.enqueue_job("poll_integration", integration_id)

    # Перевзводим сам себя. `_defer_by` гарантирует, что следующий запуск
    # будет через interval секунд от текущего, независимо от длительности
    # этого прохода.
    await pool.enqueue_job("dispatch_poll", _defer_by=timedelta(seconds=interval))
    return len(ids)


async def poll_integration(ctx: dict[str, Any], integration_id: str) -> dict[str, int]:
    """Один проход импорта для одной интеграции под локом."""
    settings = get_settings()
    window = settings.bitrix24_poll_window_days
    ttl = settings.worker_portal_lock_ttl_sec
    redis = ctx["redis"]

    async with portal_lock(redis, integration_id, ttl_sec=ttl, kind="poll") as got:
        if not got:
            logger.debug("poll: integration=%s skipped (lock held)", integration_id)
            return {"sessions": 0, "messages": 0, "skipped": 1}

        async with AsyncSessionLocal() as session:
            integration = await session.get(Integration, integration_id)
            if integration is None:
                return {"sessions": 0, "messages": 0, "skipped": 1}
            try:
                async with BitrixClient(integration, session) as client:
                    stats = await import_open_lines(
                        client, session, integration, days=window
                    )
                    await sync_portal_users_if_stale(client, session, integration)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "poll: integration=%s failed: %s", integration_id, exc
                )
                return {"sessions": 0, "messages": 0, "skipped": 1}

        if stats.messages:
            logger.info(
                "poll: integration=%s +sessions=%d +messages=%d",
                integration_id,
                stats.sessions,
                stats.messages,
            )
        return {
            "sessions": stats.sessions,
            "messages": stats.messages,
            "skipped": 0,
        }
