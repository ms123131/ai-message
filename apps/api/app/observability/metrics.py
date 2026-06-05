"""Prometheus-метрики приложения.

Подключаемые семейства:

1. **HTTP** (через `prometheus-fastapi-instrumentator`): RPS, latency,
   статусы. Идёт «из коробки» — нужно только инициализировать.
2. **Очереди arq** (gauge'ы): длина default-очереди, число дефереженных
   задач, число активных. Снимаются по запросу `/metrics` через ленивое
   обращение к Redis (graceful, если пул недоступен).
3. **LLM-латенси** (histogram): `llm_request_seconds{provider, role, ok}`.
   Декорируем вызовы провайдера в `app.integrations.llm` тонкой обёрткой.
4. **NLP pending** (gauge): сколько сообщений в каждой подсистеме ещё
   ждут обработки (sentiment_pending, tags_pending, entities_pending,
   embeddings_pending). Снимается на скрап через дешёвые COUNT-запросы.

Доступ к `/metrics` оставляем без авторизации — внутрисетевой scraper.
В проде хостинг должен ограничить доступ к нему файрволлом / private
network. Если нужно открыть наружу — обернём в Basic Auth env-флагом.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from prometheus_client import Gauge, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select

from app.db.models import Message
from app.db.session import AsyncSessionLocal
from app.observability.logging import get_logger

logger = get_logger(__name__)

# --- Семейства метрик ------------------------------------------------------

llm_request_seconds = Histogram(
    "llm_request_seconds",
    "Время одного вызова LLM-провайдера",
    labelnames=("provider", "role", "ok"),
    # Расширенные бакеты: SmartLLM может занимать 5-30с, fast обычно <2с.
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0),
)

arq_queue_size = Gauge(
    "arq_queue_size",
    "Длина очереди arq (запланированные джобы)",
    labelnames=("queue",),
)

nlp_pending_messages = Gauge(
    "nlp_pending_messages",
    "Сообщения в pending по каждой NLP-подсистеме",
    labelnames=("kind",),
)


# --- Инициализация ---------------------------------------------------------


_instrumentator: Instrumentator | None = None


def setup_metrics(app: FastAPI) -> None:
    """Регистрирует HTTP-метрики и эндпоинт /metrics."""
    global _instrumentator
    if _instrumentator is not None:
        return
    _instrumentator = (
        Instrumentator(
            # /metrics не инструментируем (иначе размер вывода растёт при
            # каждом скрапе). /api/v1/health оставляем — uptime-вероятности
            # уже отфильтруются как «успех», но это полезный сигнал жизни.
            excluded_handlers=["/metrics"],
            should_respect_env_var=False,
            should_instrument_requests_inprogress=True,
            inprogress_name="http_requests_inprogress",
        )
        .instrument(app)
        .expose(app, endpoint="/metrics", include_in_schema=False)
    )

    # Обновление динамических gauge'ов происходит middleware в main.py
    # перед скрапом /metrics. Здесь хук не нужен.


async def refresh_dynamic_gauges() -> None:
    """Лениво обновляет gauge'ы, читающиеся из БД/Redis.

    Вызывается middleware перед отдачей /metrics. Не падает, если БД или
    Redis недоступны — просто оставляет старые значения.
    """
    try:
        async with AsyncSessionLocal() as session:
            for kind, column in (
                ("sentiment", Message.sentiment),
                ("tags", Message.tags),
                ("entities", Message.entities),
                ("embeddings", Message.embedding),
            ):
                total = (
                    await session.execute(
                        select(func.count(Message.id)).where(column.is_(None))
                    )
                ).scalar_one()
                nlp_pending_messages.labels(kind=kind).set(int(total or 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_refresh_failed", error=str(exc))

    try:
        from app.workers.redis_pool import get_pool

        pool = await get_pool()
        # arq хранит запланированные джобы в zset `arq:queue` (default).
        size = await pool.zcard("arq:queue")
        arq_queue_size.labels(queue="default").set(int(size or 0))
    except Exception as exc:  # noqa: BLE001
        logger.warning("metrics_arq_refresh_failed", error=str(exc))


# --- Wrapper для LLM-запросов ---------------------------------------------


async def time_llm_call(
    *,
    provider: str,
    role: str,
    coro: Any,
) -> Any:
    """Оборачивает корутину LLM-вызова, замеряет латенси.
    `role` ∈ {"fast", "smart"}; `provider` — имя класса/строка из конфига.
    """
    import time

    start = time.perf_counter()
    ok = "true"
    try:
        return await coro
    except Exception:
        ok = "false"
        raise
    finally:
        dur = time.perf_counter() - start
        llm_request_seconds.labels(
            provider=provider or "unknown",
            role=role,
            ok=ok,
        ).observe(dur)


__all__ = [
    "arq_queue_size",
    "llm_request_seconds",
    "nlp_pending_messages",
    "refresh_dynamic_gauges",
    "setup_metrics",
    "time_llm_call",
]
