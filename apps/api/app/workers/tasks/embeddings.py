"""arq-таска: батч-расчёт эмбеддингов для одной интеграции (фаза 6.5).

По образцу sentiment/tags/entities:
- лок per-integration через `portal_lock(kind="embeddings")`;
- берёт пачку незаэмбедженных сообщений (client + agent), фильтруя
  служебные тексты Bitrix;
- считает векторы локальной моделью (`app.nlp.embeddings`) и пишет в БД.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import not_, or_, select

from app.db.models import Conversation, Message, SenderType
from app.db.session import AsyncSessionLocal
from app.nlp.bitrix_system_text import SQL_LIKE_FRAGMENTS
from app.nlp.embeddings import analyze_messages_embeddings_batch
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)

# Дефолтный размер батча — поменьше, чем у entities/sentiment: на CPU
# модель кодирует ~30-100 текстов в секунду, не хотим держать лок дольше.
_DEFAULT_BATCH_SIZE = 200


async def embed_messages_for_integration(
    ctx: dict[str, Any],
    integration_id: str,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    pool = ctx["redis"]
    async with portal_lock(
        pool, integration_id, ttl_sec=600, kind="embeddings"
    ) as got:
        if not got:
            logger.info(
                "embeddings: лок интеграции %s занят, пропускаем",
                integration_id,
            )
            return {"processed_messages": 0}

        async with AsyncSessionLocal() as session:
            ids = (
                await session.execute(
                    select(Message.id)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .where(
                        Conversation.integration_id == integration_id,
                        Message.embedding.is_(None),
                        Message.sender_type.in_(
                            [SenderType.client, SenderType.agent]
                        ),
                        not_(
                            or_(
                                *[
                                    Message.text.ilike(pattern)
                                    for pattern in SQL_LIKE_FRAGMENTS
                                ]
                            )
                        ),
                    )
                    .order_by(Message.sent_at.desc())
                    .limit(batch_size)
                )
            ).scalars().all()

            if not ids:
                logger.info(
                    "embeddings: нет новых сообщений для %s", integration_id
                )
                return {"processed_messages": 0}

            processed = await analyze_messages_embeddings_batch(
                session, list(ids)
            )
            await session.commit()
            logger.info(
                "embeddings: integration=%s processed=%d",
                integration_id,
                processed,
            )
            return {"processed_messages": processed}


__all__ = ["embed_messages_for_integration"]
