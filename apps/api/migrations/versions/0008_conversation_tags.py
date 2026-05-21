"""conversation.tags

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-21

Фаза 6.2 (доп.): денормализованные теги на уровне Conversation. Объединение
уникальных тегов из клиентских сообщений диалога — нужно для бэйджей в Inbox
и фильтрации по теме без агрегата на каждый запрос.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "tags")
