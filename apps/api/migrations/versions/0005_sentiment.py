"""message.sentiment + conversation.sentiment_score

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-20

Фаза 6.1: тональность сообщений и денормализованный агрегат по диалогу.
Тип `message_sentiment` создаётся как enum в Postgres; на SQLite Alembic
автоматически использует VARCHAR с CHECK через SAEnum.

Частичный индекс `ix_messages_sentiment_pending` ускоряет выборку
необработанных сообщений воркером (большая часть таблицы со временем
будет уже обработана, индекс компактный).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


SENTIMENT_VALUES = ("positive", "neutral", "negative")


def upgrade() -> None:
    if _is_pg():
        sentiment_enum = postgresql.ENUM(
            *SENTIMENT_VALUES, name="message_sentiment", create_type=True
        )
        sentiment_enum.create(op.get_bind(), checkfirst=True)
        op.add_column(
            "messages",
            sa.Column(
                "sentiment",
                postgresql.ENUM(
                    *SENTIMENT_VALUES,
                    name="message_sentiment",
                    create_type=False,
                ),
                nullable=True,
            ),
        )
    else:
        op.add_column(
            "messages",
            sa.Column(
                "sentiment",
                sa.Enum(*SENTIMENT_VALUES, name="message_sentiment"),
                nullable=True,
            ),
        )

    op.add_column(
        "messages",
        sa.Column("sentiment_confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("sentiment_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("sentiment_model", sa.String(100), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("sentiment_score", sa.Float(), nullable=True),
    )

    # Частичный индекс на «pending sentiment» — компактный, ускоряет
    # выборку батчей в воркере.
    if _is_pg():
        op.create_index(
            "ix_messages_sentiment_pending",
            "messages",
            ["conversation_id", "sent_at"],
            postgresql_where=sa.text("sentiment IS NULL"),
        )
    else:
        op.create_index(
            "ix_messages_sentiment_pending",
            "messages",
            ["conversation_id", "sent_at"],
            sqlite_where=sa.text("sentiment IS NULL"),
        )


def downgrade() -> None:
    op.drop_index("ix_messages_sentiment_pending", table_name="messages")
    op.drop_column("conversations", "sentiment_score")
    op.drop_column("messages", "sentiment_model")
    op.drop_column("messages", "sentiment_at")
    op.drop_column("messages", "sentiment_confidence")
    op.drop_column("messages", "sentiment")
    if _is_pg():
        postgresql.ENUM(name="message_sentiment").drop(op.get_bind(), checkfirst=True)
