"""LLM-резюме диалога через smart-провайдер (фаза 6.3).

Идея: открыл клиент 50-сообщений-длинный диалог — не хочется читать
всю простыню. Одна кнопка «Сводка» даёт 3 буллета: что произошло, что
сделал оператор, чем закончилось.

Размер контекста ограничиваем — последние N сообщений диалога.
Большинство smart-моделей принимают 128k+ токенов, но 1) дорого, 2) ранние
сообщения часто шумовые («здравствуйте»). Берём окно `_MAX_MESSAGES_IN_PROMPT`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, SenderType
from app.integrations.llm import LLMError, LLMMessage, get_llm

logger = logging.getLogger(__name__)

# Сколько последних сообщений диалога идёт в промпт. 100 закрывает 99% диалогов
# целиком и помещается в 8-16k токенов даже на дешёвых моделях.
_MAX_MESSAGES_IN_PROMPT = 100

# Кэп длины одного сообщения — обрезаем огромные простыни от клиента,
# чтобы не раздувать промпт.
_MAX_MESSAGE_CHARS = 2000

_SYSTEM_PROMPT = (
    "Ты помощник руководителя поддержки. По переписке между клиентом и "
    "оператором составь сжатую сводку РОВНО из 3 буллетов:\n"
    "• Что хотел клиент / в чём была проблема\n"
    "• Что сделал оператор\n"
    "• Чем закончилось (решено, ожидает, эскалировано)\n\n"
    "Пиши на русском, без воды, без приветствий, без markdown-заголовков. "
    "Каждый буллет — одно предложение. Если данных для буллета нет — "
    "пиши «—» вместо домыслов."
)


_ROLE_LABEL = {
    SenderType.client: "Клиент",
    SenderType.agent: "Оператор",
    SenderType.bot: "Бот",
    SenderType.system: "Система",
}


def _build_transcript(messages: list[Message]) -> str:
    lines: list[str] = []
    for m in messages:
        text = (m.text or "").strip()
        if not text:
            continue
        if len(text) > _MAX_MESSAGE_CHARS:
            text = text[:_MAX_MESSAGE_CHARS] + "…"
        role = _ROLE_LABEL.get(m.sender_type, str(m.sender_type))
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


async def summarize_conversation(
    session: AsyncSession,
    conversation_id: str,
) -> tuple[str, int, str] | None:
    """Генерирует резюме для диалога. Пишет в Conversation.

    Возвращает (summary, messages_count, model) либо None, если LLM
    недоступен/диалог пустой. Не коммитит — коммит за вызывающей стороной.
    """
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        logger.warning("summary: диалог %s не найден", conversation_id)
        return None

    # Берём последние N сообщений, потом разворачиваем в хронологию.
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sent_at.desc())
            .limit(_MAX_MESSAGES_IN_PROMPT)
        )
    ).scalars().all()
    if not rows:
        logger.info("summary: диалог %s без сообщений, пропускаем", conversation_id)
        return None
    messages = list(reversed(rows))
    transcript = _build_transcript(messages)
    if not transcript:
        logger.info("summary: диалог %s — все сообщения пустые", conversation_id)
        return None

    # Общее число сообщений диалога — для индикатора устаревания на фронте.
    total_count = (
        await session.execute(
            select(Message.id).where(Message.conversation_id == conversation_id)
        )
    ).all()
    messages_count = len(total_count)

    llm = get_llm("smart")
    try:
        resp = await llm.chat(
            [
                LLMMessage(role="system", content=_SYSTEM_PROMPT),
                LLMMessage(role="user", content=transcript),
            ],
            max_tokens=500,
            temperature=0.2,
            timeout=60.0,
        )
    except LLMError as exc:
        logger.warning("summary: LLM error для %s: %s", conversation_id, exc)
        return None

    summary = resp.content.strip()
    if not summary:
        logger.warning("summary: пустой ответ LLM для %s", conversation_id)
        return None

    now = datetime.now(UTC)
    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(
            summary=summary,
            summary_at=now,
            summary_model=resp.model,
            summary_messages_count=messages_count,
        )
    )
    return (summary, messages_count, resp.model)
