"""Детектор системных текстов Bitrix24 Open Channels.

Bitrix засылает в чаты служебные сообщения вида:

    Начат новый диалог №[URL=/online/?IM_HISTORY=imol|8]8[/URL]
    Обращение направлено на [USER=12 REPLACE]Станислав Марин[/USER]
    Закрыт диалог №[URL=...]N[/URL]
    Оператор [USER=...] переадресовал диалог на [USER=...]

Эти сообщения попадают в `imopenlines.session.history.get` и в webhook'и
с senderid != 0 (от служебного бота или оператора), поэтому наш базовый
`_sender_type()` помечает их как agent. В sentiment-анализе и в KPI
«клиентских сообщений» они только мешают: захламляют выборку и портят
средние оценки.

Используется в двух точках:
1. `app/workers/tasks/sentiment.py` — фильтр SQL `NOT LIKE`.
2. CLI-команда для пересчёта истории (см. `app/cli.py`).
"""

from __future__ import annotations

import re

# Список регулярок: если хотя бы одна совпала — текст системный.
# Все паттерны сделаны устойчивыми к регистру и к лишним пробелам.
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\[USER=\d+(?:\s+REPLACE)?\]", re.IGNORECASE),
    re.compile(r"\[URL=/online/\?IM_HISTORY=", re.IGNORECASE),
    re.compile(r"\bНачат\s+новый\s+диалог\b", re.IGNORECASE),
    re.compile(r"\bОбращение\s+направлен[оа]\s+на\b", re.IGNORECASE),
    re.compile(r"\bЗакрыт\s+диалог\b", re.IGNORECASE),
    re.compile(r"\bпереадресовал\s+диалог\b", re.IGNORECASE),
)

# SQL-эквивалент: LIKE-шаблоны (case-insensitive через ILIKE в Postgres,
# для SQLite используем lower() обёртку). Дублирует _PATTERNS точечно — то,
# что реально встречается чаще всего и тривиально мэтчится LIKE.
SQL_LIKE_FRAGMENTS: tuple[str, ...] = (
    "%[USER=%",
    "%[URL=/online/?IM_HISTORY=%",
    "%Начат новый диалог%",
    "%Обращение направлен%",
    "%Закрыт диалог%",
    "%переадресовал диалог%",
)


def is_bitrix_system_text(text: str | None) -> bool:
    """Возвращает True, если текст похож на служебное Bitrix-сообщение."""
    if not text:
        return False
    return any(p.search(text) for p in _PATTERNS)
