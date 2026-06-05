"""Эмбеддинги сообщений через sentence-transformers (фаза 6.5).

Архитектура — по образцу `app/nlp/entities.py`:

- Локальная модель `paraphrase-multilingual-MiniLM-L12-v2` (384 dim),
  работает на CPU. Lazy-init: модель грузится один раз на процесс
  (~470 МБ + чекпойнт). Воркер ставит её на старте при первом батче.
- Если `sentence-transformers` не установлен (минимальный test-runner
  или образ без torch), `_get_model()` возвращает None — батч-функция
  записывает в БД нулевые векторы и пишет в лог warning. Это позволяет
  тестам прогонять SQL-логику без скачивания 700 МБ зависимостей.

Все векторы L2-нормализуются, поэтому косинусная близость на стороне
БД (`embedding <=> :q`) превращается в простую разность 1 - dot.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Message
from app.db.types import EMBEDDING_DIM

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy init модели
# ---------------------------------------------------------------------------

_model_state: dict[str, Any] = {"loaded": None, "name": None}


def _get_model() -> tuple[Any, str] | None:
    """Возвращает (model, model_name) или None, если sentence-transformers
    недоступен. Однократная инициализация — модель ~470 МБ."""
    cached = _model_state.get("loaded")
    if cached is not None:
        if cached is False:
            return None
        return cached, _model_state["name"]

    try:
        from sentence_transformers import (  # type: ignore[import-not-found]
            SentenceTransformer,
        )
    except ImportError:
        logger.warning(
            "embeddings: sentence-transformers не установлен — эмбеддинги "
            "пропускаются; sentence-transformers ставится в основном "
            "образе worker'а (см. apps/api/pyproject.toml)"
        )
        _model_state["loaded"] = False
        return None

    settings = get_settings()
    name = settings.embeddings_model
    logger.info("embeddings: загружаем модель %s", name)
    model = SentenceTransformer(name)

    actual_dim = int(model.get_sentence_embedding_dimension() or 0)
    if actual_dim != EMBEDDING_DIM:
        # Не падаем — но настойчиво предупреждаем. Размер колонки фиксирован
        # на уровне миграции, на PG вставка несовместимого вектора упадёт
        # на стороне БД с понятной ошибкой.
        logger.error(
            "embeddings: модель %s даёт dim=%d, ожидаем %d. На pgvector "
            "вставка упадёт. Поменяйте EMBEDDINGS_MODEL или мигрируйте "
            "колонку embedding.",
            name,
            actual_dim,
            EMBEDDING_DIM,
        )

    _model_state["loaded"] = model
    _model_state["name"] = name
    return model, name


def encode_batch(texts: list[str]) -> list[list[float]] | None:
    """Кодирует список текстов в L2-нормализованные векторы.
    Возвращает None, если модель недоступна."""
    loaded = _get_model()
    if loaded is None:
        return None
    model, _name = loaded
    vectors = model.encode(
        texts,
        batch_size=min(len(texts), 32),
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


# ---------------------------------------------------------------------------
# Public batch API (вызывается из воркера)
# ---------------------------------------------------------------------------


def _prepare_text(raw: str | None, max_chars: int) -> str:
    if not raw:
        return ""
    t = raw.strip()
    if len(t) > max_chars:
        t = t[:max_chars]
    return t


async def analyze_messages_embeddings_batch(
    session: AsyncSession,
    message_ids: list[str],
) -> int:
    """Считает эмбеддинги для переданных сообщений и пишет в БД.
    Возвращает число обработанных. Не коммитит — за вызывающим.

    Пропускает сообщения, у которых уже есть embedding (idempotency на случай
    повторной постановки одного и того же id). Сообщения с пустым текстом
    помечаются нулевым вектором + meta, чтобы воркер не возвращался к ним.
    """
    if not message_ids:
        return 0

    settings = get_settings()
    rows = (
        await session.execute(select(Message).where(Message.id.in_(message_ids)))
    ).scalars().all()

    pending: list[Message] = []
    texts: list[str] = []
    written_empty = 0
    for msg in rows:
        if msg.embedding is not None:
            continue
        text = _prepare_text(msg.text, settings.embeddings_max_chars)
        if not text:
            # Пустой текст — пишем нулевой вектор, чтобы воркер не возвращался.
            msg.embedding = [0.0] * EMBEDDING_DIM
            msg.embedding_at = datetime.now(UTC)
            msg.embedding_model = settings.embeddings_model
            written_empty += 1
            continue
        pending.append(msg)
        texts.append(text)

    if not pending:
        return written_empty

    vectors = encode_batch(texts)
    if vectors is None:
        logger.warning(
            "embeddings: модель недоступна, %d сообщений останутся pending",
            len(pending),
        )
        return written_empty

    now = datetime.now(UTC)
    model_name = _model_state.get("name") or settings.embeddings_model
    for msg, vec in zip(pending, vectors, strict=True):
        msg.embedding = vec
        msg.embedding_at = now
        msg.embedding_model = model_name

    return written_empty + len(pending)


__all__ = [
    "EMBEDDING_DIM",
    "analyze_messages_embeddings_batch",
    "encode_batch",
]
