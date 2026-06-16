"""Сборка промпта для AI-ассистента: system + бизнес-профиль + контекст диалогов.

Принцип грудинга: модель отвечает ТОЛЬКО на основе предоставленных диалогов и
профиля бизнеса; если данных мало — должна честно это сказать, а не выдумывать.
Источники цитируются по conversation_id в формате [#id], фронт превращает их
в ссылки на /inbox/:id.
"""

from __future__ import annotations

from app.config import get_settings
from app.integrations.llm.base import LLMMessage
from app.services.ai_assistant.retrieval import RetrievedConversation

_SYSTEM_BASE = (
    "Ты — AI-аналитик клиентской поддержки внутри сервиса аналитики переписки. "
    "Твоя задача — помогать команде поддержки: разбирать темы обращений, "
    "находить слабые места, подсказывать, что и как улучшить, как корректно "
    "вести себя с клиентами.\n\n"
    "Правила:\n"
    "1. Отвечай ТОЛЬКО на основе профиля бизнеса и приведённых диалогов/сводок. "
    "Не придумывай факты, которых нет в данных.\n"
    "2. Если данных недостаточно для ответа — прямо скажи об этом и предложи, "
    "что уточнить или какие диалоги посмотреть.\n"
    "3. Ссылайся на конкретные диалоги-источники в формате [#conversation_id].\n"
    "4. Отвечай по-русски, кратко и по делу, с конкретными рекомендациями.\n"
)


def _render_context(items: list[RetrievedConversation]) -> str:
    blocks: list[str] = []
    for it in items:
        parts = [f"### Диалог [#{it.conversation_id}] — {it.title}"]
        if it.summary:
            parts.append(f"Резюме: {it.summary}")
        if it.snippets:
            quoted = "\n".join(f"  • {s}" for s in it.snippets)
            parts.append(f"Фрагменты:\n{quoted}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def build_system_prompt(
    *,
    business_profile: str | None,
    items: list[RetrievedConversation],
    weak_spots: str | None = None,
) -> str:
    """Собирает system-сообщение с учётом кэпа на длину контекста."""
    max_chars = get_settings().ai_assistant_max_context_chars
    sections = [_SYSTEM_BASE]

    if business_profile and business_profile.strip():
        sections.append("## Профиль бизнеса\n" + business_profile.strip())

    if weak_spots:
        sections.append("## Сводка по проблемным зонам (агрегат по всем диалогам)\n" + weak_spots)

    context = _render_context(items)
    if context:
        # Режем контекст, а не профиль/правила — они дешёвые и важные.
        budget = max_chars - sum(len(s) for s in sections)
        if budget > 0 and len(context) > budget:
            context = context[:budget] + "\n…(контекст обрезан)"
        sections.append("## Релевантные диалоги\n" + context)
    else:
        sections.append(
            "## Релевантные диалоги\n(по запросу не нашлось подходящих диалогов)"
        )

    return "\n\n".join(sections)


def build_messages(
    *,
    system_prompt: str,
    history: list[LLMMessage],
    question: str,
) -> list[LLMMessage]:
    turns = get_settings().ai_assistant_history_turns
    trimmed = history[-turns * 2 :] if turns > 0 else []
    return [
        LLMMessage(role="system", content=system_prompt),
        *trimmed,
        LLMMessage(role="user", content=question),
    ]
