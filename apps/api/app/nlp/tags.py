"""Авто-тегирование сообщений тем через fast-LLM (фаза 6.2).

Идея проста: ставим клиентскому сообщению 0-3 темы из заранее заданного
словаря (Settings.tags_vocabulary). Это «теги» одновременно для:
- агрегата по порталу («о чём чаще пишут») — см. /dashboard/tags;
- атрибутов диалога (бэйджи в Inbox);
- фильтра в Inbox по теме.

Промпт коротко: «верни через запятую 1-3 темы из списка, либо `none`».
Парсер устойчив: режет пробелы/пунктуацию, мэтчит slug регистронезависимо,
оставляет только то, что есть в словаре.

Используется fast-LLM (один общий с sentiment), потому что задача массовая
и не нюансовая. На smart переходить не нужно — он дороже.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Message
from app.integrations.llm import LLMError, LLMMessage, get_llm

logger = logging.getLogger(__name__)

# Слишком короткие сообщения тегировать бессмысленно (типа «ок», «спасибо»).
_MIN_TEXT_LEN = 8
# Лимит на максимум тем в одном сообщении — больше 3 LLM начинает выдумывать.
_MAX_TAGS_PER_MESSAGE = 3

_SPECIAL_NONE_TOKENS = {"none", "нет", "—", "-", ""}


def get_vocabulary() -> list[str]:
    """Возвращает текущий словарь тегов (slug'ов) из конфига."""
    raw = get_settings().tags_vocabulary
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def _format_vocabulary(vocab: list[str]) -> str:
    """Готовит человекочитаемое перечисление для промпта.

    Slug'и хранятся со снэйк-кейсом (`статус_заказа`), модели проще понять
    с пробелами. Возвращаем JSON-подобный list, чтобы LLM не выдумывала
    свой формат.
    """
    return ", ".join(s.replace("_", " ") for s in vocab)


_PROMPT_TEMPLATE = (
    "Ты классификатор тем для обращений клиентов в поддержку. "
    "Выбери 1-3 темы из ЭТОГО списка, которые лучше всего описывают "
    "сообщение клиента. Темы:\n{vocab}\n\n"
    "Правила:\n"
    "- Отвечай только slug'ами через запятую, ровно как в списке "
    "(пробелы заменяй на подчёркивания).\n"
    "- Если ни одна тема не подходит — ответь `none`.\n"
    "- Никаких комментариев, заголовков и кавычек.\n"
)


def _parse_tags(raw: str, vocab: list[str]) -> list[str]:
    """Из ответа модели достаёт список валидных slug'ов.

    Толерантно к мусору: модель может разделить пробелами/запятыми,
    добавить кавычки, написать `тег_1, тег_2 - возможно`. Мы берём
    только те токены, что точно из словаря.
    """
    if not raw:
        return []
    # Приводим к slug-форме: lower, пробелы → подчёркивания.
    cleaned = raw.lower().strip().strip("\"'.,;:!?()[]{}\n\r\t ")
    if cleaned in _SPECIAL_NONE_TOKENS:
        return []

    # Разделители: запятая, точка с запятой, перевод строки, слеш.
    parts = re.split(r"[,;\n/]+", cleaned)
    vocab_set = set(vocab)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        # Внутри части могут остаться пробелы вокруг slug'а.
        token = part.strip().strip("\"'.,;:!?()[]{}")
        if not token or token in _SPECIAL_NONE_TOKENS:
            continue
        # Допускаем форму с пробелами вместо подчёркиваний.
        normalized = re.sub(r"\s+", "_", token)
        if normalized in vocab_set and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
        if len(result) >= _MAX_TAGS_PER_MESSAGE:
            break
    return result


async def classify_tags(text: str, vocab: list[str]) -> tuple[list[str], str] | None:
    """Классифицирует один текст. Возвращает (tags, model) либо None при
    недоступности/ошибке LLM. Пустой список тегов — валидный результат
    («ни одна из тем не подходит»), он будет записан в БД, чтобы не
    переанализировать в следующий батч.
    """
    if not text or len(text.strip()) < _MIN_TEXT_LEN:
        return ([], "trivial")
    if not vocab:
        # Словарь пуст — ничего не классифицируем, но и не считаем ошибкой.
        return ([], "empty_vocab")

    llm = get_llm("fast")
    try:
        resp = await llm.chat(
            [
                LLMMessage(
                    role="system",
                    content=_PROMPT_TEMPLATE.format(vocab=_format_vocabulary(vocab)),
                ),
                LLMMessage(role="user", content=text[:4000]),
            ],
            max_tokens=32,
            temperature=0.0,
        )
    except LLMError as exc:
        logger.warning("tags LLM error: %s", exc)
        return None

    tags = _parse_tags(resp.content, vocab)
    return (tags, resp.model)


async def analyze_messages_tags_batch(
    session: AsyncSession,
    message_ids: list[str],
) -> int:
    """Тегирует переданные сообщения. Возвращает число обработанных
    (включая записанные с пустым списком). Не коммитит — за вызывающим.
    """
    if not message_ids:
        return 0
    vocab = get_vocabulary()
    rows = (
        await session.execute(select(Message).where(Message.id.in_(message_ids)))
    ).scalars().all()

    processed = 0
    now = datetime.now(UTC)
    for msg in rows:
        if msg.tags is not None:
            continue
        result = await classify_tags(msg.text or "", vocab)
        if result is None:
            continue
        tags, model = result
        msg.tags = tags
        msg.tags_at = now
        msg.tags_model = model
        processed += 1
    return processed
