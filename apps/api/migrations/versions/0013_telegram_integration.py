"""telegram_user/telegram_bot/whatsapp_user в Integration + поля auth_blob/health

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-08

Расширение enum'ов integration_kind/integration_mode под новые типы коннекторов
(см. docs/PLAN_CONNECTORS.md) и три служебных поля:

- auth_blob       — шифрованный StringSession (Telethon) или creds (Baileys).
- webhook_secret  — шифрованный секрет для входящего webhook.
- last_health_*   — состояние периодической проверки подключения.

На SQLite enum'ы хранятся как VARCHAR, поэтому ALTER TYPE нужен только для PG.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_KINDS = ("telegram_bot", "telegram_user", "whatsapp_user")
_NEW_MODES = ("bot_token", "qr_link", "mtproto_session", "wazzup_token")


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_pg():
        # ALTER TYPE ... ADD VALUE не работает в транзакции до PG12 и требует
        # autocommit-блок в Alembic. PG12+ поддерживает IF NOT EXISTS.
        with op.get_context().autocommit_block():
            for v in _NEW_KINDS:
                op.execute(
                    f"ALTER TYPE integration_kind ADD VALUE IF NOT EXISTS '{v}'"
                )
            for v in _NEW_MODES:
                op.execute(
                    f"ALTER TYPE integration_mode ADD VALUE IF NOT EXISTS '{v}'"
                )

    # EncryptedString наследуется от Text — храним ciphertext (base64).
    op.add_column(
        "integrations",
        sa.Column("auth_blob", sa.Text(), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("webhook_secret", sa.Text(), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("last_health_status", sa.String(40), nullable=True),
    )
    op.add_column(
        "integrations",
        sa.Column("last_health_detail", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    # Удаляем колонки. Откатить ALTER TYPE ADD VALUE без полного пересоздания
    # типа нельзя — оставляем enum-значения, это не ломает старые записи.
    op.drop_column("integrations", "last_health_detail")
    op.drop_column("integrations", "last_health_status")
    op.drop_column("integrations", "last_health_at")
    op.drop_column("integrations", "webhook_secret")
    op.drop_column("integrations", "auth_blob")
