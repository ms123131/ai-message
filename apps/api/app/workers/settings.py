"""WorkerSettings для arq.

Запуск из контейнера: `arq app.workers.settings.WorkerSettings` (см.
`entrypoint.sh: run-worker`).

На старте воркер ставит единственный `dispatch_poll`-джоб, который дальше
сам перевзводится через `_defer_by`. Так избегаем cron-разметки на любой
интервал из env (поддерживаются произвольные значения, не только делители 60с).
"""

from __future__ import annotations

import logging

from app.workers.redis_pool import redis_settings
from app.workers.tasks.bitrix_import import run_import_job_task
from app.workers.tasks.bitrix_poll import dispatch_poll, poll_integration
from app.workers.tasks.conversation_enrich import enrich_conversation_from_chat
from app.workers.tasks.crm_sync import dispatch_crm_sync, sync_crm_for_integration
from app.workers.tasks.sentiment import analyze_sentiment_for_integration
from app.workers.tasks.summary import summarize_conversation_task

logger = logging.getLogger(__name__)


async def _on_startup(ctx: dict) -> None:
    """Стартовый bootstrap: ставим первый dispatch_poll. Дальше он
    перевзводится сам. ID джоба фиксированный — это гарантирует, что
    при рестарте воркера НЕ образуется дубль (arq дедуплицирует по job_id).
    """
    pool = ctx["redis"]
    await pool.enqueue_job("dispatch_poll", _job_id="bootstrap-dispatch-poll")
    await pool.enqueue_job(
        "dispatch_crm_sync", _job_id="bootstrap-dispatch-crm-sync"
    )
    logger.info("worker started; dispatch_poll + dispatch_crm_sync bootstrapped")


async def _on_shutdown(ctx: dict) -> None:  # noqa: ARG001
    logger.info("worker shutting down")


class WorkerSettings:
    functions = [
        dispatch_poll,
        poll_integration,
        run_import_job_task,
        dispatch_crm_sync,
        sync_crm_for_integration,
        enrich_conversation_from_chat,
        analyze_sentiment_for_integration,
        summarize_conversation_task,
    ]
    redis_settings = redis_settings()
    on_startup = _on_startup
    on_shutdown = _on_shutdown
    # Сколько джобов одновременно в одном процессе воркера.
    max_jobs = 10
    # Сколько ретраев у самой задачи (arq добавляет каждой по умолчанию 5);
    # для нас важнее, чтобы не залипали бесконечно при системных проблемах.
    max_tries = 3
    # Если ничего нет в очереди — лонг-поллинг 500мс, чтобы CPU не крутился.
    poll_delay = 0.5
