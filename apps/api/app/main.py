import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.config import get_settings
from app.db.session import engine
from app.workers.redis_pool import close_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ai-message")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Схема БД создаётся миграциями Alembic вне процесса API
    # (см. compose-сервис `migrate`).
    # Фоновый поллинг и импорт теперь делает отдельный воркер-контейнер
    # (`compose worker`), API только enqueue-ит задачи в Redis.
    logger.info("ai-message api v%s started", __version__)
    try:
        yield
    finally:
        await close_pool()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ai-message API",
        version=__version__,
        description="Chat Analysis platform — REST API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
