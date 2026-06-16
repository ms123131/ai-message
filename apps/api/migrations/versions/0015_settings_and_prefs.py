"""settings & prefs: tenant регион/тариф + user ui_preferences/sessions_revoked_at

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-16

Расширяет Tenant полями для вкладки Settings → Компания (timezone, locale) и
Оплата (plan, trial_ends_at). В users добавляет ui_preferences (раскладка
настраиваемого KPI-дашборда, JSON) и sessions_revoked_at («выйти со всех
устройств» — отсечка по iat refresh-токена).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("locale", sa.String(8), nullable=False, server_default="ru"),
    )
    op.add_column(
        "tenants",
        sa.Column("plan", sa.String(32), nullable=False, server_default="trial"),
    )
    op.add_column(
        "tenants",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column("users", sa.Column("ui_preferences", sa.JSON(), nullable=True))
    op.add_column(
        "users",
        sa.Column("sessions_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "sessions_revoked_at")
    op.drop_column("users", "ui_preferences")
    op.drop_column("tenants", "trial_ends_at")
    op.drop_column("tenants", "plan")
    op.drop_column("tenants", "locale")
    op.drop_column("tenants", "timezone")
