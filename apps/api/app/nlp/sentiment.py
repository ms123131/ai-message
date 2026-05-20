"""Sentiment-классификация сообщений через fast-LLM.

Структура:
- `classify(text)` — один вызов LLM, возвращает (Sentiment, confidence).
  Промпт прости-нелепый специально: одно слово в ответ, чтобы парсинг
  не зависел от того, умеет ли модель валидный JSON выдавать.
- `analyze_messages_batch(session, message_ids)` — батчевая обёртка:
  пробегает по сообщениям, классифицирует, пишет sentiment + sentiment_at +
  sentiment_model. Не падает на одиночной ошибке провайдера — лог +
  оставляем sentiment NULL (попадёт в следующий батч).
- `recompute_conversation_sentiment_score(session, conv_id)` — пересчитывает
  агрегированный score диалога [-1, 1] из sentiment его клиентских
  сообщений (сообщения операторов в score не входят: нас интересует
  настроение клиента).

Тональность только клиентских сообщений: дашборд показывает «как клиент
себя чувствует», а не «как говорит менеджер».
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message, SenderType, Sentiment
from app.integrations.llm import LLMError, LLMMessage, get_llm

logger = logging.getLogger(__name__)

# Системный промпт. Жёсткий формат: одно слово, никаких комментариев.
# Многоязычность нужна — клиенты пишут на RU и EN.
_SYSTEM_PROMPT = (
    "You are a sentiment classifier for customer support messages. "
    "Reply with EXACTLY ONE word — positive, neutral, or negative — "
    "based on the emotional tone of the message. No punctuation, no "
    "explanation, no quotes. Works for Russian and English messages."
)

# Минимальная длина текста, который имеет смысл классифицировать.
# Эмодзи или «ок» классифицируем как neutral без LLM-вызова, экономим токены.
_MIN_TEXT_LEN = 4

# Соответствие тональности — числовая шкала для агрегата по диалогу.
_SENTIMENT_TO_SCORE: dict[Sentiment, float] = {
    Sentiment.positive: 1.0,
    Sentiment.neutral: 0.0,
    Sentiment.negative: -1.0,
}


def _parse_sentiment(raw: str) -> Sentiment | None:
    """Извлекает sentiment из ответа модели. Терпим к мусору вокруг."""
    s = raw.strip().lower()
    # Часто модели обрамляют ответ кавычками или пунктуацией.
    s = s.strip("\"'.,;:!?()[]{}\n\r\t ")
    # Берём первое слово, если модель всё-таки развернулась.
    first = s.split()[0] if s else ""
    if first.startswith("pos"):
        return Sentiment.positive
    if first.startswith("neg"):
        return Sentiment.negative
    if first.startswith("neu"):
        return Sentiment.neutral
    return None


async def classify(text: str) -> tuple[Sentiment, float, str] | None:
    """Классифицирует один текст. Возвращает (sentiment, confidence, model)
    или None — если LLM недоступен/не распарсили. Confidence — грубая оценка
    (1.0 — распарсили чистый ответ, 0.5 — извлекли из мусора).
    """
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return (Sentiment.neutral, 1.0, "trivial")

    llm = get_llm("fast")
    try:
        resp = await llm.chat(
            [
                LLMMessage(role="system", content=_SYSTEM_PROMPT),
                LLMMessage(role="user", content=text[:4000]),
            ],
            max_tokens=8,
            temperature=0.0,
        )
    except LLMError as exc:
        logger.warning("sentiment LLM error: %s", exc)
        return None

    sentiment = _parse_sentiment(resp.content)
    if sentiment is None:
        logger.warning("sentiment parse failed: raw=%r", resp.content[:100])
        return None

    # Confidence: если ответ ровно одним словом — 1.0; если в нём ещё что-то —
    # 0.6 (модель неаккуратна, но мы извлекли смысл).
    confidence = 1.0 if len(resp.content.strip().split()) == 1 else 0.6
    return (sentiment, confidence, resp.model)


async def analyze_messages_batch(
    session: AsyncSession,
    message_ids: list[str],
) -> int:
    """Классифицирует переданные сообщения, пишет результаты в БД.

    Возвращает число успешно обработанных сообщений. Не коммитит —
    коммит за вызывающей стороной (worker-task).
    """
    if not message_ids:
        return 0

    rows = (
        await session.execute(
            select(Message).where(Message.id.in_(message_ids))
        )
    ).scalars().all()

    processed = 0
    now = datetime.now(UTC)
    for msg in rows:
        if msg.sentiment is not None:
            # Кто-то уже обработал — пропускаем
            continue
        result = await classify(msg.text or "")
        if result is None:
            continue
        sentiment, confidence, model = result
        msg.sentiment = sentiment
        msg.sentiment_confidence = confidence
        msg.sentiment_at = now
        msg.sentiment_model = model
        processed += 1
    return processed


async def recompute_conversation_sentiment_score(
    session: AsyncSession,
    conversation_id: str,
) -> float | None:
    """Пересчитывает Conversation.sentiment_score из sentiment клиентских
    сообщений. Возвращает значение либо None если нет проанализированных
    клиентских сообщений. Не коммитит.
    """
    expr = case(
        (Message.sentiment == Sentiment.positive, _SENTIMENT_TO_SCORE[Sentiment.positive]),
        (Message.sentiment == Sentiment.negative, _SENTIMENT_TO_SCORE[Sentiment.negative]),
        (Message.sentiment == Sentiment.neutral, _SENTIMENT_TO_SCORE[Sentiment.neutral]),
        else_=None,
    )
    avg = (
        await session.execute(
            select(func.avg(expr)).where(
                Message.conversation_id == conversation_id,
                Message.sender_type == SenderType.client,
                Message.sentiment.is_not(None),
            )
        )
    ).scalar()

    score = float(avg) if avg is not None else None
    await session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(sentiment_score=score)
    )
    return score
