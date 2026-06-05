from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app import __version__
from app.api.v1 import api_router
from app.config import get_settings
from app.db.session import engine
from app.integrations.llm import reset_cache as reset_llm_cache
from app.observability import RequestIdMiddleware, get_logger, setup_logging
from app.observability.metrics import refresh_dynamic_gauges, setup_metrics
from app.observability.middleware import _add_request_id_header
from app.security.ratelimit import limiter, rate_limit_exceeded_handler
from app.workers.redis_pool import close_pool

# Логи: JSON в проде/тесте, человекочитаемые в dev.
_settings = get_settings()
setup_logging(json_logs=not _settings.is_dev, level="INFO")
logger = get_logger("ai-message")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Схема БД создаётся миграциями Alembic вне процесса API
    # (см. compose-сервис `migrate`).
    # Фоновый поллинг и импорт теперь делает отдельный воркер-контейнер
    # (`compose worker`), API только enqueue-ит задачи в Redis.
    logger.info("api_started", version=__version__)
    try:
        yield
    finally:
        await close_pool()
        await reset_llm_cache()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ai-message API",
        version=__version__,
        description="Chat Analysis platform — REST API",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    # Порядок middleware важен: starlette применяет в обратном порядке
    # добавления, поэтому RequestId должен быть добавлен ПОСЛЕДНИМ, чтобы
    # сработать ПЕРВЫМ (обернуть всех остальных). Так request_id будет в
    # contextvars к моменту, когда любой нижестоящий код пишет лог.
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(_add_request_id_header)
    app.add_middleware(RequestIdMiddleware)

    @app.middleware("http")
    async def _refresh_metrics_on_scrape(request, call_next):
        # Перед скрапом /metrics обновляем динамические gauge'ы (NLP pending,
        # длина arq-очереди). На прочих запросах no-op.
        if request.url.path == "/metrics":
            await refresh_dynamic_gauges()
        return await call_next(request)

    setup_metrics(app)
    app.include_router(api_router)
    return app


app = create_app()
