"""arq-таска: батч-извлечение сущностей для одной интеграции (фаза 6.6).

В отличие от sentiment/tags обрабатываем сообщения ВСЕХ типов sender_type —
почта оператора, телефон в подписи, ссылки от клиента нужны одинаково.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.db.models import Conversation, Message
from app.db.session import AsyncSessionLocal
from app.nlp.entities import analyze_messages_entities_batch
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)

# Natasha-инициализация дорогая, но один раз на процесс. После неё батч
# в 500 сообщений отрабатывает за секунды.
_DEFAULT_BATCH_SIZE = 500


async def analyze_entities_for_integration(
    ctx: dict[str, Any],
    integration_id: str,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    pool = ctx["redis"]
    async with portal_lock(
        pool, integration_id, ttl_sec=600, kind="entities"
    ) as got:
        if not got:
            logger.info(
                "entities: лок интеграции %s занят, пропускаем", integration_id
            )
            return {"processed_messages": 0}

        async with AsyncSessionLocal() as session:
            ids = (
                await session.execute(
                    select(Message.id)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .where(
                        Conversation.integration_id == integration_id,
                        Message.entities.is_(None),
                    )
                    .order_by(Message.sent_at.desc())
                    .limit(batch_size)
                )
            ).scalars().all()

            if not ids:
                logger.info("entities: нет новых сообщений для %s", integration_id)
                return {"processed_messages": 0}

            processed = await analyze_messages_entities_batch(session, list(ids))
            await session.commit()
            logger.info(
                "entities: integration=%s processed=%d", integration_id, processed
            )
            return {"processed_messages": processed}


__all__ = ["analyze_entities_for_integration"]
