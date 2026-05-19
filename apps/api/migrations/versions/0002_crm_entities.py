"""crm entities, conversation_crm_links, portal_stages

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-19

Спринт 1 связки «диалог → CRM»: новые таблицы для хранения сущностей
Lead/Deal/Contact/Company портала Bitrix24, их семантики (won/lost/in_progress)
и многозначной связи `conversation_crm_links`. `portal_stages` — кэш справочника
стадий, нужен импортёру для перевода `STAGE_ID` → семантика без вызовов REST
на каждый ряд.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    crm_entity_kind = postgresql.ENUM(
        "lead", "deal", "contact", "company",
        name="crm_entity_kind",
        create_type=False,
    )
    crm_stage_semantics = postgresql.ENUM(
        "in_progress", "won", "lost",
        name="crm_stage_semantics",
        create_type=False,
    )
    if _is_pg():
        crm_entity_kind.create(op.get_bind(), checkfirst=True)
        crm_stage_semantics.create(op.get_bind(), checkfirst=True)

    # crm_entities
    op.create_table(
        "crm_entities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "integration_id",
            sa.String(64),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", crm_entity_kind, nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("stage_external_id", sa.String(64), nullable=True),
        sa.Column(
            "status_semantics",
            crm_stage_semantics,
            nullable=False,
            server_default="in_progress",
        ),
        # Numeric достаточно широкий, чтобы вместить любые суммы из B24.
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("assigned_user_id", sa.String(128), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        "uq_crm_entities_integration_kind_external",
        "crm_entities",
        ["integration_id", "kind", "external_id"],
        unique=True,
    )
    op.create_index(
        "ix_crm_entities_integration_kind_status",
        "crm_entities",
        ["integration_id", "kind", "status_semantics"],
    )

    # conversation_crm_links
    op.create_table(
        "conversation_crm_links",
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "crm_entity_id",
            sa.String(64),
            sa.ForeignKey("crm_entities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_crm_links_entity",
        "conversation_crm_links",
        ["crm_entity_id"],
    )

    # portal_stages
    op.create_table(
        "portal_stages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "integration_id",
            sa.String(64),
            sa.ForeignKey("integrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_kind", crm_entity_kind, nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column(
            "semantics",
            crm_stage_semantics,
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("sort", sa.Integer, nullable=True),
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
        "uq_portal_stages_integration_kind_external",
        "portal_stages",
        ["integration_id", "entity_kind", "external_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_portal_stages_integration_kind_external", table_name="portal_stages"
    )
    op.drop_table("portal_stages")

    op.drop_index(
        "ix_conversation_crm_links_entity", table_name="conversation_crm_links"
    )
    op.drop_table("conversation_crm_links")

    op.drop_index(
        "ix_crm_entities_integration_kind_status", table_name="crm_entities"
    )
    op.drop_index(
        "uq_crm_entities_integration_kind_external", table_name="crm_entities"
    )
    op.drop_table("crm_entities")

    if _is_pg():
        op.execute("DROP TYPE IF EXISTS crm_stage_semantics")
        op.execute("DROP TYPE IF EXISTS crm_entity_kind")
    _ = postgresql  # noqa: F841
