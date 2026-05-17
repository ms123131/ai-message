"""
Фоновый поллинг Bitrix24 Open Channels.

Bitrix24 не доставляет события `OnOpenLineMessageAdd` приложениям, которые
не зарегистрировали свой коннектор через `imconnector.register`. Для
универсального приложения (без своего коннектора) единственный надёжный
способ получать новые сообщения — периодически опрашивать im.recent.get +
imopenlines.session.history.get. Используем готовый `import_open_lines`,
он сам делает upsert/дедуп.

Запуск — из lifespan FastAPI. Корректное завершение по cancel.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Integration, IntegrationMode, IntegrationStatus
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.importer import import_open_lines

logger = logging.getLogger(__name__)


async def _poll_once(window_days: int) -> None:
    """Один проход поллера: дёргает import для каждой OAuth-интеграции."""
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Integration).where(
                Integration.mode == IntegrationMode.oauth,
                Integration.status == IntegrationStatus.connected,
            )
        )
        integrations = list(rows.scalars().all())

    for integration in integrations:
        try:
            async with AsyncSessionLocal() as session:
                # SQLAlchemy не разрешает использовать объект из закрытой
                # сессии — берём свежий по id.
                fresh = await session.get(Integration, integration.id)
                if not fresh:
                    continue
                async with BitrixClient(fresh, session) as client:
                    stats = await import_open_lines(
                        client, session, fresh, days=window_days
                    )
                if stats.messages:
                    logger.info(
                        "poll: integration=%s +sessions=%d +messages=%d",
                        fresh.id,
                        stats.sessions,
                        stats.messages,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("poll: integration=%s failed: %s", integration.id, exc)


async def run_forever() -> None:
    settings = get_settings()
    interval = settings.bitrix24_poll_interval_sec
    window = settings.bitrix24_poll_window_days
    if interval <= 0:
        logger.info("bitrix24 poller disabled (interval=0)")
        # Висим до отмены — Event.wait() даёт штатный cancel при shutdown.
        await asyncio.Event().wait()
        return  # pragma: no cover

    logger.info(
        "bitrix24 poller started: interval=%ds window=%dd", interval, window
    )
    while True:
        try:
            await _poll_once(window)
        except Exception as exc:  # noqa: BLE001 — на всякий случай, _poll_once уже ловит
            logger.exception("poller loop error: %s", exc)
        await asyncio.sleep(interval)
