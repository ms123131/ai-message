"""message.tags + tags_at + tags_model

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-22

Фаза 6.2: авто-теги тем для сообщений клиентов. Поле tags хранится как JSON
(list[str]) — простота важнее нормализации, тегов в одном сообщении 0-3.
Дашборд агрегирует через jsonb_array_elements (Postgres) либо json_each (SQLite).

Частичный индекс ix_messages_tags_pending ускоряет выборку батчей воркером.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column("messages", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("tags_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages", sa.Column("tags_model", sa.String(100), nullable=True)
    )

    if _is_pg():
        op.create_index(
            "ix_messages_tags_pending",
            "messages",
            ["conversation_id", "sent_at"],
            postgresql_where=sa.text("tags IS NULL"),
        )
    else:
        op.create_index(
            "ix_messages_tags_pending",
            "messages",
            ["conversation_id", "sent_at"],
            sqlite_where=sa.text("tags IS NULL"),
        )


def downgrade() -> None:
    op.drop_index("ix_messages_tags_pending", table_name="messages")
    op.drop_column("messages", "tags_model")
    op.drop_column("messages", "tags_at")
    op.drop_column("messages", "tags")
