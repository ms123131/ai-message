"""Дельта-синхронизация CRM-сущностей независимо от активности чатов.

Проблема: при переходе сделки в won/lost событие происходит в CRM, а не
в Open Channels. Если у диалога нет новых сообщений, основной поллер не
дёрнет связанные с ним сделки — наша таблица `crm_entities` останется
со старым `status_semantics` и конверсия в дашборде не обновится.

Решение: `dispatch_crm_sync` ставит `sync_crm_for_integration` на каждую
подключённую интеграцию и перевзводит сам себя через
`bitrix24_crm_sync_interval_sec` (по умолчанию 5 минут).
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
from app.integrations.bitrix24.crm import refresh_known_crm_entities
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)


async def dispatch_crm_sync(ctx: dict[str, Any]) -> int:
    """Диспетчер дельта-sync'а CRM. Self-rescheduling по `bitrix24_crm_sync_interval_sec`."""
    settings = get_settings()
    interval = settings.bitrix24_crm_sync_interval_sec
    if interval <= 0:
        logger.info("crm delta sync disabled (interval=0)")
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
        await pool.enqueue_job("sync_crm_for_integration", integration_id)

    await pool.enqueue_job(
        "dispatch_crm_sync", _defer_by=timedelta(seconds=interval)
    )
    return len(ids)


async def sync_crm_for_integration(
    ctx: dict[str, Any], integration_id: str
) -> dict[str, int]:
    """Освежает все CrmEntity одной интеграции через `crm.deal.list`/
    `crm.lead.list` + справочник стадий. Берёт тот же `kind=poll` лок,
    что и основной поллер, — нельзя крутить два REST-marathon'а одновременно.
    """
    settings = get_settings()
    ttl = settings.worker_portal_lock_ttl_sec
    redis = ctx["redis"]

    async with portal_lock(redis, integration_id, ttl_sec=ttl, kind="poll") as got:
        if not got:
            logger.debug(
                "crm sync: integration=%s skipped (lock held)", integration_id
            )
            return {"updated": 0, "skipped": 1}

        async with AsyncSessionLocal() as session:
            integration = await session.get(Integration, integration_id)
            if integration is None:
                return {"updated": 0, "skipped": 1}
            try:
                async with BitrixClient(integration, session) as client:
                    updated = await refresh_known_crm_entities(
                        client, session, integration
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "crm sync: integration=%s failed: %s", integration_id, exc
                )
                return {"updated": 0, "skipped": 1}

        if updated:
            logger.info(
                "crm sync: integration=%s refreshed=%d entities",
                integration_id,
                updated,
            )
        return {"updated": updated, "skipped": 0}
