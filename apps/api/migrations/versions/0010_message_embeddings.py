"""message.embedding + embedding_at + embedding_model

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-05

Фаза 6.5: эмбеддинги сообщений (sentence-transformers
paraphrase-multilingual-MiniLM-L12-v2, 384-dim). На Postgres колонка
имеет тип pgvector.Vector(384), на SQLite (тесты) — JSON со списком
float'ов. Семантический поиск похожих диалогов идёт через cosine
distance (оператор `<=>` в pgvector), индекс ivfflat lists=100.

Частичный индекс ix_messages_embedding_pending — для выборки батчей
воркером embed_messages_for_integration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMBEDDING_DIM = 384


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_pg():
        # Расширение pgvector. В образе pgvector/pgvector:pg16 уже доступно,
        # достаточно включить в текущей БД. IF NOT EXISTS — идемпотентность.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute(
            f"ALTER TABLE messages ADD COLUMN embedding vector({EMBEDDING_DIM})"
        )
    else:
        # SQLite: храним JSON-список float'ов. Семантический поиск на SQLite
        # не работает (только в тестах с stub-encoder'ом), но поле должно
        # существовать для совместимости моделей.
        op.add_column("messages", sa.Column("embedding", sa.JSON(), nullable=True))

    op.add_column(
        "messages",
        sa.Column("embedding_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("embedding_model", sa.String(length=100), nullable=True),
    )

    if _is_pg():
        op.create_index(
            "ix_messages_embedding_pending",
            "messages",
            ["conversation_id", "sent_at"],
            postgresql_where=sa.text("embedding IS NULL"),
        )
        # ivfflat по cosine. lists=100 — разумный дефолт до ~1М векторов;
        # на больших объёмах подбирается как sqrt(N). Индекс строится на
        # пустой таблице мгновенно, ANALYZE добавится при первом батче.
        op.execute(
            "CREATE INDEX ix_messages_embedding_cosine "
            "ON messages USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 100)"
        )
    else:
        op.create_index(
            "ix_messages_embedding_pending",
            "messages",
            ["conversation_id", "sent_at"],
            sqlite_where=sa.text("embedding IS NULL"),
        )


def downgrade() -> None:
    if _is_pg():
        op.execute("DROP INDEX IF EXISTS ix_messages_embedding_cosine")
    op.drop_index("ix_messages_embedding_pending", table_name="messages")
    op.drop_column("messages", "embedding_model")
    op.drop_column("messages", "embedding_at")
    op.drop_column("messages", "embedding")
    # CREATE EXTENSION оставляем — другие миграции/таблицы могут на него
    # рассчитывать. Если действительно нужно убрать — делается отдельной
    # миграцией с DROP EXTENSION vector CASCADE.
