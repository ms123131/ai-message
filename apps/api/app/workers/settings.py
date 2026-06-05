"""WorkerSettings для arq.

Запуск из контейнера: `arq app.workers.settings.WorkerSettings` (см.
`entrypoint.sh: run-worker`).

На старте воркер ставит единственный `dispatch_poll`-джоб, который дальше
сам перевзводится через `_defer_by`. Так избегаем cron-разметки на любой
интервал из env (поддерживаются произвольные значения, не только делители 60с).
"""

from __future__ import annotations

import logging

from arq import cron

from app.config import get_settings
from app.workers.redis_pool import redis_settings
from app.workers.tasks.bitrix_import import run_import_job_task
from app.workers.tasks.bitrix_poll import dispatch_poll, poll_integration
from app.workers.tasks.conversation_enrich import enrich_conversation_from_chat
from app.workers.tasks.crm_sync import dispatch_crm_sync, sync_crm_for_integration
from app.workers.tasks.embeddings import embed_messages_for_integration
from app.workers.tasks.entities import analyze_entities_for_integration
from app.workers.tasks.nlp_cron import nlp_dispatch_cron
from app.workers.tasks.sentiment import analyze_sentiment_for_integration
from app.workers.tasks.summary import summarize_conversation_task
from app.workers.tasks.tags import analyze_tags_for_integration

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
        analyze_tags_for_integration,
        analyze_entities_for_integration,
        embed_messages_for_integration,
        summarize_conversation_task,
        nlp_dispatch_cron,
    ]
    # Авто-запуск sentiment+tags по cron, если включено в env.
    # arq.cron поддерживает поминутный интервал — собираем set минут вида
    # {0, K, 2K, ...} ограниченный набором из 0..59. K=0 → пустой набор,
    # cron не сработает (фактическое отключение).
    _interval = max(0, get_settings().nlp_cron_interval_minutes)
    cron_jobs = (
        [
            cron(
                nlp_dispatch_cron,
                minute={m for m in range(0, 60, _interval)},
                run_at_startup=False,
                unique=True,
            )
        ]
        if _interval > 0
        else []
    )
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
