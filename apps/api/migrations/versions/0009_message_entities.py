"""message.entities + entities_at

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-21

Фаза 6.6: извлечение сущностей (телефон, email, URL, трек-номер, сумма,
имя, город, организация) через Natasha + регулярки. Хранится как JSON
({"phone": [...], "email": [...], ...}). Частичный индекс
ix_messages_entities_pending — для выборки батчей воркером.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column("messages", sa.Column("entities", sa.JSON(), nullable=True))
    op.add_column(
        "messages",
        sa.Column("entities_at", sa.DateTime(timezone=True), nullable=True),
    )

    if _is_pg():
        op.create_index(
            "ix_messages_entities_pending",
            "messages",
            ["conversation_id", "sent_at"],
            postgresql_where=sa.text("entities IS NULL"),
        )
    else:
        op.create_index(
            "ix_messages_entities_pending",
            "messages",
            ["conversation_id", "sent_at"],
            sqlite_where=sa.text("entities IS NULL"),
        )


def downgrade() -> None:
    op.drop_index("ix_messages_entities_pending", table_name="messages")
    op.drop_column("messages", "entities_at")
    op.drop_column("messages", "entities")
