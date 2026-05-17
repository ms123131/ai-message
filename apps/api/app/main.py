import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.config import get_settings
from app.db.session import Base, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ai-message")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # На старте MVP создаём таблицы напрямую через SQLAlchemy.
    # Alembic-миграции добавятся, когда схема стабилизируется.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("ai-message api v%s started", __version__)
    yield
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
