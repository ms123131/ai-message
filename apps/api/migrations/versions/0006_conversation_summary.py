"""conversation.summary + summary_at + summary_model + summary_messages_count

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-21

Фаза 6.3: LLM-резюме диалогов (smart-провайдер). Поля денормализованы
на Conversation, чтобы Inbox мог отдавать summary в одном запросе.
`summary_messages_count` — счётчик сообщений на момент генерации, фронт
сравнивает с актуальным `message_count` и подсвечивает «устарело».
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("summary_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations", sa.Column("summary_model", sa.String(100), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("summary_messages_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "summary_messages_count")
    op.drop_column("conversations", "summary_model")
    op.drop_column("conversations", "summary_at")
    op.drop_column("conversations", "summary")
