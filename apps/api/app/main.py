import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.config import get_settings
from app.db.session import Base, engine
from app.integrations.bitrix24.poller import run_forever as run_bitrix24_poller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ai-message")


async def _ensure_schema_patches() -> None:
    """
    Идемпотентные DDL-патчи для уже существующих БД. `Base.metadata.create_all`
    не добавляет новые колонки в существующие таблицы и не дропает старые,
    поэтому каждое расширение модели требует ручного ALTER TABLE.

    Для SQLite (тесты/локальный dev) ничего не нужно: схема создаётся с нуля.
    Когда схема стабилизируется — заменим на Alembic.
    """
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return

    statements = [
        # Фаза 4: tenant_id в integrations (для multi-tenancy).
        "ALTER TABLE integrations ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64)",
        "CREATE INDEX IF NOT EXISTS ix_integrations_tenant_id ON integrations(tenant_id)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'integrations_tenant_id_fkey'
            ) THEN
                ALTER TABLE integrations
                ADD CONSTRAINT integrations_tenant_id_fkey
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
            END IF;
        END $$;
        """,
        # Фаза 4.5: webhook-режим интеграции удалён — чистим старые записи,
        # иначе SQLAlchemy не сможет загрузить их (значения нет в enum).
        "DELETE FROM integrations WHERE mode::text = 'webhook'",
        # Фаза 5 (дашборд): расширение Conversation для аналитики.
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS assigned_user_id VARCHAR(128)",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS line_id VARCHAR(64)",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS first_message_at TIMESTAMPTZ",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS first_agent_reply_at TIMESTAMPTZ",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ",
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS response_time_sec INTEGER",
        "CREATE INDEX IF NOT EXISTS ix_conversations_integration_assigned ON conversations(integration_id, assigned_user_id)",
        "CREATE INDEX IF NOT EXISTS ix_conversations_integration_status_updated ON conversations(integration_id, status, updated_at)",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.warning("schema patch failed (%s): %s", stmt.split()[0], exc)


async def _attach_orphan_integrations_to_first_tenant() -> None:
    """
    Одноразовая миграция данных: до фазы 4 интеграции создавались без tenant_id.
    Привязываем их к первому существующему tenant'у, если он уже создан
    (через регистрацию первого пользователя). Если ни одного tenant ещё нет —
    оставляем как есть; миграция произойдёт при следующем старте после регистрации.
    """
    from sqlalchemy import select, update

    from app.db.models import Integration, Tenant
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        first_tenant = (
            await session.execute(select(Tenant).order_by(Tenant.created_at).limit(1))
        ).scalar_one_or_none()
        if not first_tenant:
            return
        result = await session.execute(
            update(Integration)
            .where(Integration.tenant_id.is_(None))
            .values(tenant_id=first_tenant.id)
        )
        if result.rowcount:
            logger.info(
                "migrated %d orphan integration(s) to tenant=%s",
                result.rowcount,
                first_tenant.id,
            )
        await session.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # На старте MVP создаём таблицы напрямую через SQLAlchemy.
    # Alembic-миграции добавятся, когда схема стабилизируется.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_schema_patches()
    await _attach_orphan_integrations_to_first_tenant()
    logger.info("ai-message api v%s started", __version__)

    poller_task = asyncio.create_task(run_bitrix24_poller(), name="bitrix24-poller")
    try:
        yield
    finally:
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.warning("poller exited with error: %s", exc)
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
