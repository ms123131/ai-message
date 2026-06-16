"""ai-ассистент: ai_threads + ai_messages + tenants.ai_business_profile

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-16

Хранилище для чат-ассистента «спроси свою переписку» (planApp.md B10, v1):
- `ai_threads` — тред диалога пользователя с ассистентом (per-tenant);
- `ai_messages` — реплики треда (user/assistant), у assistant-реплик в JSON
  `sources` лежат ссылки на диалоги-источники, а также модель и учёт токенов
  (поля под будущий контроль расходов, B9);
- `tenants.ai_business_profile` — текстовый профиль бизнеса (сфера, продукты,
  tone of voice, политики), который подмешивается в system-промпт ассистента.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("ai_business_profile", sa.Text(), nullable=True),
    )

    op.create_table(
        "ai_threads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Список тредов tenant'а, свежие сверху.
    op.create_index(
        "ix_ai_threads_tenant_updated",
        "ai_threads",
        ["tenant_id", "updated_at"],
    )

    op.create_table(
        "ai_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "thread_id",
            sa.String(64),
            sa.ForeignKey("ai_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="ai_message_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Загрузка реплик треда в хронологии.
    op.create_index(
        "ix_ai_messages_thread_created",
        "ai_messages",
        ["thread_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_messages_thread_created", table_name="ai_messages")
    op.drop_table("ai_messages")
    op.drop_index("ix_ai_threads_tenant_updated", table_name="ai_threads")
    op.drop_table("ai_threads")
    op.drop_column("tenants", "ai_business_profile")
    # Явно убираем enum-тип на Postgres (SQLite его не создаёт).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="ai_message_role").drop(bind, checkfirst=True)
