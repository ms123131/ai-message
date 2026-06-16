"""Лёгкий агрегат «слабых мест» для ассистента (v1, дешёвый компромисс).

Чистый RAG плохо отвечает на «где у нас провалы», поэтому, когда вопрос
похож на запрос о проблемах, подмешиваем в контекст компактную сводку:
сколько негативных диалогов, сколько без ответа оператора, какие темы чаще
всего всплывают в негативе. Это не полноценная аналитика с tool-use (v2),
но даёт ассистенту фактуру для осмысленного ответа уже в v1.

Запросы tenant-safe (JOIN через integrations) и портативны между PG и SQLite.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, ConversationStatus, Integration

# Порог тональности диалога — согласован с conversations.py (SENTIMENT_THRESHOLD).
_NEGATIVE_THRESHOLD = -0.2

# Триггер-слова: включаем сводку только для вопросов «про проблемы».
_WEAK_SPOT_HINTS = (
    "слаб",
    "проблем",
    "провал",
    "улучш",
    "недовол",
    "жалоб",
    "негатив",
    "ошиб",
    "что не так",
    "плохо",
    "риск",
    "теря",
    "отток",
    "churn",
    "weak",
    "improve",
    "problem",
)


def looks_like_weak_spot_query(query: str) -> bool:
    q = query.lower()
    return any(hint in q for hint in _WEAK_SPOT_HINTS)


async def compute_weak_spots(
    session: AsyncSession, tenant_id: str
) -> str | None:
    """Текстовая сводка проблемных зон tenant'а или None, если данных нет."""
    base = (
        select(Conversation)
        .join(Integration, Integration.id == Conversation.integration_id)
        .where(Integration.tenant_id == tenant_id)
    )

    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    if not total:
        return None

    negative = await session.scalar(
        select(func.count()).select_from(
            base.where(Conversation.sentiment_score < _NEGATIVE_THRESHOLD).subquery()
        )
    )
    unanswered = await session.scalar(
        select(func.count()).select_from(
            base.where(
                Conversation.status == ConversationStatus.open,
                Conversation.first_agent_reply_at.is_(None),
                Conversation.first_message_at.is_not(None),
            ).subquery()
        )
    )

    # Темы негативных диалогов: tags хранятся JSON-списком, агрегируем в Python.
    neg_tag_rows = (
        await session.execute(
            base.where(
                Conversation.sentiment_score < _NEGATIVE_THRESHOLD,
                Conversation.tags.is_not(None),
            ).with_only_columns(Conversation.tags)
        )
    ).all()
    tag_counter: Counter[str] = Counter()
    for (tags,) in neg_tag_rows:
        if tags:
            tag_counter.update(tags)
    top_tags = tag_counter.most_common(5)

    lines = [
        f"- всего диалогов: {total}",
        f"- негативных (по тональности): {negative or 0}",
        f"- без ответа оператора (открытых): {unanswered or 0}",
    ]
    if top_tags:
        tags_str = ", ".join(f"{slug} ({cnt})" for slug, cnt in top_tags)
        lines.append(f"- частые темы в негативе: {tags_str}")
    return "\n".join(lines)
