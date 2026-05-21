"""arq-таска: батч-классификация sentiment для одной интеграции.

Не делаем диспетчера с self-scheduling, как у poll: sentiment не нужен
в реальном времени, достаточно ручного триггера через API после импорта
или один раз в сутки. Если позже понадобится — добавим dispatch_sentiment
по аналогии с poll.

Под distributed-локом per-integration: чтобы две реплики воркера не
обрабатывали одни и те же сообщения, тратя в 2 раза больше токенов.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import not_, or_, select

from app.db.models import Conversation, Message, SenderType, Sentiment
from app.db.session import AsyncSessionLocal
from app.nlp.bitrix_system_text import SQL_LIKE_FRAGMENTS
from app.nlp.sentiment import (
    analyze_messages_batch,
    recompute_conversation_sentiment_score,
)
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)

# Сколько сообщений берём за один проход. Большее значение = меньше
# overhead на установление LLM-соединения, но дольше держим лок.
_DEFAULT_BATCH_SIZE = 200


async def analyze_sentiment_for_integration(
    ctx: dict[str, Any],
    integration_id: str,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    """Берёт необработанные сообщения интеграции (sentiment IS NULL),
    классифицирует через fast-LLM, пересчитывает агрегаты диалогов.

    Один проход. Если в БД ещё остались необработанные — следующий проход
    нужно запустить отдельно (через API-триггер или cron). Это сознательно:
    мы не хотим, чтобы одна интеграция бесконечно блокировала очередь.
    """
    pool = ctx["redis"]
    # ttl=600с: один проход обычно укладывается в 1-2 минуты даже на тысячи
    # сообщений, но LLM-провайдер может тормозить. kind=sentiment, чтобы не
    # конфликтовать с poll-локом для той же интеграции.
    async with portal_lock(pool, integration_id, ttl_sec=600, kind="sentiment") as got:
        if not got:
            logger.info(
                "sentiment: лок интеграции %s занят, пропускаем", integration_id
            )
            return {"processed_messages": 0, "updated_conversations": 0}

        async with AsyncSessionLocal() as session:
            # Берём ID необработанных сообщений в диалогах этой интеграции.
            ids = (
                await session.execute(
                    select(Message.id)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .where(
                        Conversation.integration_id == integration_id,
                        Message.sentiment.is_(None),
                        # Дашборд и agg по диалогу считают только клиентские
                        # сообщения. Sentiment для сообщений операторов нигде
                        # не используется — нет смысла тратить на них токены.
                        Message.sender_type == SenderType.client,
                        # Bitrix-служебные тексты ("Начат новый диалог №...",
                        # "[USER=...]" и т.п.) не несут эмоции — исключаем
                        # ещё на SQL-уровне, чтобы не дёргать LLM на них.
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
                logger.info("sentiment: нет новых сообщений для %s", integration_id)
                return {"processed_messages": 0, "updated_conversations": 0}

            processed = await analyze_messages_batch(session, list(ids))

            # Пересчитываем агрегат у диалогов, где появились новые sentiment.
            conv_ids = (
                await session.execute(
                    select(Message.conversation_id)
                    .where(
                        Message.id.in_(list(ids)),
                        Message.sentiment.is_not(None),
                    )
                    .distinct()
                )
            ).scalars().all()
            for cid in conv_ids:
                await recompute_conversation_sentiment_score(session, cid)

            await session.commit()

            logger.info(
                "sentiment: integration=%s processed=%d conversations_updated=%d",
                integration_id,
                processed,
                len(conv_ids),
            )
            return {
                "processed_messages": processed,
                "updated_conversations": len(conv_ids),
            }


# Защита от случайного импорта: явные имена для arq registry.
__all__ = ["analyze_sentiment_for_integration"]


# Удобный mapping для тестов / отладки — не используется в проде.
_SENTIMENT_LABELS = {s.value for s in Sentiment}
