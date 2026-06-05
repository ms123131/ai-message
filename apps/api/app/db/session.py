from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_dev,
    future=True,
)


# SQLite по умолчанию игнорирует FOREIGN KEY и ON DELETE CASCADE.
# В тестах используется sqlite, поэтому включаем enforcement на каждое соединение.
# Заодно регистрируем Unicode-aware LOWER (стандартный SQLite lower() — ASCII only,
# из-за чего поиск по кириллице в нижнем регистре не находил CAPS-сообщения).
@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, _record):
    module = dbapi_connection.__class__.__module__
    if "sqlite" not in module and "aiosqlite" not in module:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
    # Перебиваем встроенный lower() Python-функцией, которая знает про
    # Unicode case folding. На больших объёмах — медленнее, но в dev/test
    # это ОК; на проде используется PG FTS, эта функция не вызывается.
    try:
        dbapi_connection.create_function("lower", 1, lambda s: s.lower() if s else s)
    except Exception:  # noqa: BLE001 — старые драйверы без create_function
        pass

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
