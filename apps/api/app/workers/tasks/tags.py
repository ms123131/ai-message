"""arq-таска: батч-тегирование сообщений интеграции через fast-LLM (фаза 6.2).

Архитектурно повторяет sentiment-таску (см. tasks/sentiment.py):
- per-integration distributed-lock (kind=tags, чтобы не конфликтовать с sentiment);
- выборка batch_size клиентских сообщений с tags IS NULL;
- фильтрация Bitrix-служебных текстов на SQL-уровне;
- без recompute_conversation_score — тегам агрегат на уровне дашборда (top-N).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import not_, or_, select

from app.db.models import Conversation, Message, SenderType
from app.db.session import AsyncSessionLocal
from app.nlp.bitrix_system_text import SQL_LIKE_FRAGMENTS
from app.nlp.tags import analyze_messages_tags_batch
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 200


async def analyze_tags_for_integration(
    ctx: dict[str, Any],
    integration_id: str,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    pool = ctx["redis"]
    async with portal_lock(
        pool, integration_id, ttl_sec=600, kind="tags"
    ) as got:
        if not got:
            logger.info(
                "tags: лок интеграции %s занят, пропускаем", integration_id
            )
            return {"processed_messages": 0}

        async with AsyncSessionLocal() as session:
            ids = (
                await session.execute(
                    select(Message.id)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .where(
                        Conversation.integration_id == integration_id,
                        Message.tags.is_(None),
                        Message.sender_type == SenderType.client,
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
                logger.info("tags: нет новых сообщений для %s", integration_id)
                return {"processed_messages": 0}

            processed = await analyze_messages_tags_batch(session, list(ids))
            await session.commit()
            logger.info(
                "tags: integration=%s processed=%d", integration_id, processed
            )
            return {"processed_messages": processed}


__all__ = ["analyze_tags_for_integration"]
