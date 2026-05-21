"""arq-таска: LLM-резюме одного диалога через smart-провайдер.

Лок per-conversation, чтобы повторный клик «Сводка» в Inbox не запускал
параллельные генерации (smart-модели дороже fast: лучше дождаться первой).
TTL лока меньше, чем у sentiment (60с вместо 600с), потому что один диалог
обычно укладывается в несколько секунд.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.session import AsyncSessionLocal
from app.nlp.summary import summarize_conversation
from app.workers.locks import portal_lock

logger = logging.getLogger(__name__)


async def summarize_conversation_task(
    ctx: dict[str, Any],
    conversation_id: str,
) -> dict[str, Any]:
    pool = ctx["redis"]
    # Используем portal_lock с conversation_id вместо integration_id —
    # реализация ключа допускает любой строковый идентификатор; kind=summary
    # обеспечивает изоляцию от sentiment-лока.
    async with portal_lock(
        pool, conversation_id, ttl_sec=60, kind="summary"
    ) as got:
        if not got:
            logger.info(
                "summary: лок диалога %s занят, пропускаем", conversation_id
            )
            return {"status": "skipped_locked", "conversation_id": conversation_id}

        async with AsyncSessionLocal() as session:
            result = await summarize_conversation(session, conversation_id)
            if result is None:
                await session.rollback()
                return {
                    "status": "no_result",
                    "conversation_id": conversation_id,
                }
            summary, messages_count, model = result
            await session.commit()
            logger.info(
                "summary: conversation=%s model=%s messages=%d chars=%d",
                conversation_id,
                model,
                messages_count,
                len(summary),
            )
            return {
                "status": "ok",
                "conversation_id": conversation_id,
                "model": model,
                "messages_count": messages_count,
            }


__all__ = ["summarize_conversation_task"]
