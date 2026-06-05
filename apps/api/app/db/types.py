"""Кастомные SQLAlchemy-типы для проекта (фаза 6.5).

`EmbeddingVector` — кросс-диалектный тип для эмбеддингов сообщений:
- на Postgres хранится как `vector(384)` из pgvector (нужно для cosine
  поиска через оператор `<=>` и ivfflat-индекса);
- на SQLite (тесты) хранится как JSON-список float'ов.

Импорт pgvector защищён try/except: если пакет недоступен (минимальное
test-окружение), на PG будет fallback в JSON. В реальном проде pgvector
включён в зависимости.
"""

from __future__ import annotations

from sqlalchemy import JSON as SAJSON
from sqlalchemy.types import TypeDecorator

EMBEDDING_DIM = 384

try:
    from pgvector.sqlalchemy import Vector  # type: ignore[import-not-found]

    _PG_VECTOR_TYPE = Vector(EMBEDDING_DIM)
    _HAS_PGVECTOR = True
except ImportError:  # pragma: no cover — на тестовом образе без pgvector
    _PG_VECTOR_TYPE = SAJSON()
    _HAS_PGVECTOR = False


class EmbeddingVector(TypeDecorator):
    """Vector(384) на Postgres, JSON-список на SQLite."""

    impl = SAJSON
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql" and _HAS_PGVECTOR:
            return dialect.type_descriptor(_PG_VECTOR_TYPE)
        return dialect.type_descriptor(SAJSON())


__all__ = ["EMBEDDING_DIM", "EmbeddingVector"]
