"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-19

Создаёт всю текущую схему ai-message с нуля. Поскольку до этой ревизии
проект жил на `Base.metadata.create_all` без боевых данных, baseline
тривиален: одна миграция = вся схема. Все ENUM-типы создаются явно
до `create_table`, чтобы переиспользуемые (`conversation_channel`)
не падали на повторном CREATE TYPE.

FTS-колонка `messages.tsv` и GIN-индекс — только для PostgreSQL.
SQLite в тестах сюда не приходит (использует `Base.metadata.create_all`),
но условные ветки оставлены на случай ручного `alembic upgrade` против sqlite.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONVERSATION_CHANNEL_VALUES = (
    "whatsapp",
    "telegram",
    "vk",
    "instagram",
    "facebook",
    "livechat",
    "email",
    "other",
)


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ENUM-типы создаём заранее, чтобы переиспользовать в нескольких таблицах
    # без падения на повторном CREATE TYPE.
    # Используем postgresql.ENUM с create_type=False — только этот класс
    # уважает флаг и не пытается CREATE TYPE при create_table.
    # Сами типы создаём отдельно перед таблицами.
    user_role = postgresql.ENUM(
        "admin", "member", name="user_role", create_type=False
    )
    integration_kind = postgresql.ENUM(
        "bitrix24", name="integration_kind", create_type=False
    )
    integration_mode = postgresql.ENUM(
        "oauth", name="integration_mode", create_type=False
    )
    integration_status = postgresql.ENUM(
        "pending", "connected", "error", name="integration_status", create_type=False
    )
    conversation_channel = postgresql.ENUM(
        *CONVERSATION_CHANNEL_VALUES,
        name="conversation_channel",
        create_type=False,
    )
    conversation_status = postgresql.ENUM(
        "open", "closed", name="conversation_status", create_type=False
    )
    message_sender_type = postgresql.ENUM(
        "client",
        "agent",
        "bot",
        "system",
        name="message_sender_type",
        create_type=False,
    )
    import_job_status = postgresql.ENUM(
        "pending",
        "running",
        "done",
        "failed",
        name="import_job_status",
        create_type=False,
    )

    if _is_pg():
        for enum_t in (
            user_role,
            integration_kind,
            integration_mode,
            integration_status,
            conversation_channel,
            conversation_status,
            message_sender_type,
            import_job_status,
        ):
            enum_t.create(op.get_bind(), checkfirst=True)

    # tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default="member"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # integrations
    op.create_table(
        "integrations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", integration_kind, nullable=False),
        sa.Column("mode", integration_mode, nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column(
            "status",
            integration_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("client_id", sa.String(255), nullable=True),
        sa.Column("client_secret", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text, nullable=True),
        sa.Column("refresh_token", sa.Text, nullable=True),
        sa.Column("member_id", sa.String(100), nullable=True),
        sa.Column("scope", sa.String(500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_integrations_tenant_id", "integrations", ["tenant_id"])

    # conversations
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "integration_id",
            sa.String(64),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("channel", conversation_channel, nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("contact_external_id", sa.String(128), nullable=True),
        sa.Column(
            "status",
            conversation_status,
            nullable=False,
            server_default="open",
        ),
        sa.Column("assigned_user_id", sa.String(128), nullable=True),
        sa.Column("line_id", sa.String(64), nullable=True),
        sa.Column("first_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_agent_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_time_sec", sa.Integer, nullable=True),
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
    op.create_index(
        "ix_conversations_integration_created",
        "conversations",
        ["integration_id", "created_at"],
    )
    op.create_index(
        "ix_conversations_integration_assigned",
        "conversations",
        ["integration_id", "assigned_user_id"],
    )
    op.create_index(
        "ix_conversations_integration_status_updated",
        "conversations",
        ["integration_id", "status", "updated_at"],
    )
    op.create_index(
        "uq_conversations_integration_external",
        "conversations",
        ["integration_id", "external_id"],
        unique=True,
    )

    # messages
    op.create_table(
        "messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("sender_type", message_sender_type, nullable=False),
        sa.Column("sender_external_id", sa.String(128), nullable=True),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("attachments", sa.JSON, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_messages_conversation_sent", "messages", ["conversation_id", "sent_at"]
    )
    # Partial unique index — только для Postgres (SQLite понимает синтаксис,
    # но в этой миграции под sqlite не приходим). Используем postgresql_where.
    op.create_index(
        "uq_messages_conversation_external",
        "messages",
        ["conversation_id", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
        sqlite_where=sa.text("external_id IS NOT NULL"),
    )

    # Полнотекстовый поиск (только Postgres)
    if _is_pg():
        op.execute(
            "ALTER TABLE messages "
            "ADD COLUMN tsv tsvector GENERATED ALWAYS AS "
            "(to_tsvector('russian', coalesce(text, ''))) STORED"
        )
        op.execute(
            "CREATE INDEX ix_messages_tsv ON messages USING GIN (tsv)"
        )

    # portal_users
    op.create_table(
        "portal_users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "integration_id",
            sa.String(64),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("work_position", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_portal_users_integration_external",
        "portal_users",
        ["integration_id", "external_id"],
        unique=True,
    )

    # portal_lines
    op.create_table(
        "portal_lines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "integration_id",
            sa.String(64),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_portal_lines_integration_external",
        "portal_lines",
        ["integration_id", "external_id"],
        unique=True,
    )

    # sla_targets
    op.create_table(
        "sla_targets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(64),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            postgresql.ENUM(
                *CONVERSATION_CHANNEL_VALUES,
                name="conversation_channel",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("threshold_minutes", sa.Integer, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_sla_targets_tenant_channel",
        "sla_targets",
        ["tenant_id", "channel"],
        unique=True,
    )

    # import_jobs
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "integration_id",
            sa.String(64),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            import_job_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("days", sa.Integer, nullable=False, server_default="30"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "processed_sessions", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "processed_messages", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_import_jobs_integration_created",
        "import_jobs",
        ["integration_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_jobs_integration_created", table_name="import_jobs")
    op.drop_table("import_jobs")

    op.drop_index("uq_sla_targets_tenant_channel", table_name="sla_targets")
    op.drop_table("sla_targets")

    op.drop_index("uq_portal_lines_integration_external", table_name="portal_lines")
    op.drop_table("portal_lines")

    op.drop_index("uq_portal_users_integration_external", table_name="portal_users")
    op.drop_table("portal_users")

    if _is_pg():
        op.execute("DROP INDEX IF EXISTS ix_messages_tsv")
    op.drop_index("uq_messages_conversation_external", table_name="messages")
    op.drop_index("ix_messages_conversation_sent", table_name="messages")
    op.drop_table("messages")

    op.drop_index(
        "uq_conversations_integration_external", table_name="conversations"
    )
    op.drop_index(
        "ix_conversations_integration_status_updated", table_name="conversations"
    )
    op.drop_index(
        "ix_conversations_integration_assigned", table_name="conversations"
    )
    op.drop_index("ix_conversations_integration_created", table_name="conversations")
    op.drop_table("conversations")

    op.drop_index("ix_integrations_tenant_id", table_name="integrations")
    op.drop_table("integrations")

    op.drop_table("users")
    op.drop_table("tenants")

    if _is_pg():
        for enum_name in (
            "import_job_status",
            "message_sender_type",
            "conversation_status",
            "conversation_channel",
            "integration_status",
            "integration_mode",
            "integration_kind",
            "user_role",
        ):
            op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    # Линтер postgresql import используется тестово; явный no-op для импорта.
    _ = postgresql  # noqa: F841
