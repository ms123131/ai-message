"""Cron-таска: автоматический запуск sentiment + tags по всем интеграциям.

Включается, если `NLP_CRON_INTERVAL_MINUTES > 0`. Каждый запуск:
- проходит по всем connected-интеграциям всех tenant'ов;
- enqueue'ит `analyze_sentiment_for_integration` и `analyze_tags_for_integration`
  с batch_size из настроек.

Лок per-integration внутри самих таск-обработчиков предохраняет от наслоения
с ручным триггером через API.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Integration, IntegrationStatus
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def nlp_dispatch_cron(ctx: dict[str, Any]) -> dict[str, int]:
    """Раздаёт NLP-задачи на все подключённые интеграции."""
    settings = get_settings()
    if settings.nlp_cron_interval_minutes <= 0:
        return {"skipped": 1}

    pool = ctx["redis"]
    batch_size = settings.nlp_cron_batch_size

    async with AsyncSessionLocal() as session:
        integrations = (
            await session.execute(
                select(Integration.id).where(
                    Integration.status == IntegrationStatus.connected
                )
            )
        ).scalars().all()

    if not integrations:
        return {"integrations": 0}

    enqueued = 0
    for integration_id in integrations:
        await pool.enqueue_job(
            "analyze_sentiment_for_integration", integration_id, batch_size
        )
        await pool.enqueue_job(
            "analyze_tags_for_integration", integration_id, batch_size
        )
        await pool.enqueue_job(
            "analyze_entities_for_integration", integration_id, batch_size
        )
        enqueued += 3
    logger.info(
        "nlp_cron: integrations=%d enqueued=%d", len(integrations), enqueued
    )
    return {"integrations": len(integrations), "enqueued": enqueued}


__all__ = ["nlp_dispatch_cron"]
