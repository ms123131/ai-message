"""email verification: users.email_verified_at + auth_tokens

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-13

Подтверждение email (Hard-confirm) и сброс пароля. В users добавляется
email_verified_at (NULL = не подтверждён). auth_tokens хранит одноразовые
токены: в БД только sha256-хэш, сырой токен — лишь в ссылке письма.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "type",
            sa.Enum("verify", "reset", name="auth_token_type"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_auth_tokens_token_hash",
        "auth_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_tokens_user_type",
        "auth_tokens",
        ["user_id", "type"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_tokens_user_type", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_token_hash", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_column("users", "email_verified_at")
    sa.Enum(name="auth_token_type").drop(op.get_bind(), checkfirst=True)
