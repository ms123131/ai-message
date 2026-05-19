"""Задача исторического импорта.

Запускается из `/integrations/{id}/import` через `enqueue_job`. Берёт
тот же лок `kind=poll`, что и фоновый поллер, — поллер и ручной импорт
не должны идти одновременно по одному порталу.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.db.models import ImportJob, Integration
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.importer import run_import_job
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)


async def run_import_job_task(
    ctx: dict[str, Any], integration_id: str, job_id: str
) -> str:
    """Прогоняет ImportJob по id. Возвращает финальный status строкой.

    Если лок взять не удалось (поллер сейчас крутит ту же интеграцию),
    задача отложится через arq retry — но в нашем сценарии импорта это
    редкий случай, поэтому просто ждём в очереди — следующий тик поллера
    освободит лок. Здесь мы просто помечаем job как failed, чтобы UI
    показал внятный статус, а не вечный pending.
    """
    settings = get_settings()
    ttl = settings.worker_portal_lock_ttl_sec
    redis = ctx["redis"]

    async with portal_lock(redis, integration_id, ttl_sec=ttl, kind="poll") as got:
        async with AsyncSessionLocal() as session:
            job = await session.get(ImportJob, job_id)
            integration = await session.get(Integration, integration_id)
            if job is None or integration is None:
                logger.warning(
                    "import job %s or integration %s not found",
                    job_id,
                    integration_id,
                )
                return "missing"
            if not got:
                # Лок занят. Помечаем failed с понятным сообщением — пользователь
                # увидит причину и сможет перезапустить.
                from app.db.models import ImportJobStatus

                job.status = ImportJobStatus.failed
                job.error = "Портал занят другим импортом, попробуйте позже"
                await session.commit()
                return "locked"

            async with BitrixClient(integration, session) as client:
                await run_import_job(client, session, job, integration)
            await session.refresh(job)
            return job.status.value if hasattr(job.status, "value") else str(job.status)
