"""conversation.embedding_centroid (фаза 7.4 — оптимизация /similar)

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-05

Денормализуем центроид эмбеддингов диалога, чтобы `/conversations/{id}/similar`
не тянул все векторы исходного диалога в Python и не считал среднее на
каждом запросе. Воркер `embed_messages_for_integration` пересчитывает
центроид после каждого батча новых эмбеддингов через AVG-окно по
сообщениям диалога.

На Postgres — `vector(384)`, на SQLite (тесты) — JSON-список (как для
Message.embedding в миграции 0010).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EMBEDDING_DIM = 384


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_pg():
        op.execute(
            f"ALTER TABLE conversations "
            f"ADD COLUMN embedding_centroid vector({EMBEDDING_DIM})"
        )
    else:
        op.add_column(
            "conversations",
            sa.Column("embedding_centroid", sa.JSON(), nullable=True),
        )

    op.add_column(
        "conversations",
        sa.Column(
            "embedding_centroid_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    if _is_pg():
        # ivfflat-индекс на centroid — для быстрого top-K похожих диалогов
        # без агрегации по сообщениям (сейчас в /similar мы группируем
        # MIN(distance) по conversation_id, что O(N сообщений)).
        op.execute(
            "CREATE INDEX ix_conversations_centroid_cosine "
            "ON conversations USING ivfflat "
            "(embedding_centroid vector_cosine_ops) WITH (lists = 100)"
        )


def downgrade() -> None:
    if _is_pg():
        op.execute("DROP INDEX IF EXISTS ix_conversations_centroid_cosine")
    op.drop_column("conversations", "embedding_centroid_at")
    op.drop_column("conversations", "embedding_centroid")
