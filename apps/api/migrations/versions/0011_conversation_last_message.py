"""conversation.last_message_at + last_message_preview + backfill

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-05

Денормализация ради cursor-пагинации Inbox: раньше последний таймстемп
вычислялся подзапросом GROUP BY на messages, плюс отдельный проход за
превью. На 100k диалогов это уже секунды; cursor через LIMIT/OFFSET по
композитному (last_at, conv_id) превращается в seq-scan.

Backfill идёт одним UPDATE: подтягиваем MAX(sent_at) и LIMIT 1 текст
последнего сообщения на каждый conversation.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("last_message_preview", sa.String(length=200), nullable=True),
    )
    op.create_index(
        "ix_conversations_last_message",
        "conversations",
        ["last_message_at", "id"],
    )

    if _is_pg():
        # PG: один UPDATE с подзапросом — last_message + первая строка
        # текста через DISTINCT ON.
        op.execute(
            """
            UPDATE conversations c
               SET last_message_at = m.last_at,
                   last_message_preview = LEFT(m.last_text, 200)
              FROM (
                SELECT DISTINCT ON (conversation_id)
                       conversation_id,
                       sent_at AS last_at,
                       text     AS last_text
                  FROM messages
                 ORDER BY conversation_id, sent_at DESC
              ) m
             WHERE m.conversation_id = c.id
            """
        )
    else:
        # SQLite: коррелированные подзапросы. Простой и переносимый вариант.
        op.execute(
            """
            UPDATE conversations
               SET last_message_at = (
                       SELECT MAX(sent_at) FROM messages
                        WHERE messages.conversation_id = conversations.id
                   ),
                   last_message_preview = (
                       SELECT substr(text, 1, 200) FROM messages
                        WHERE messages.conversation_id = conversations.id
                        ORDER BY sent_at DESC
                        LIMIT 1
                   )
            """
        )


def downgrade() -> None:
    op.drop_index("ix_conversations_last_message", table_name="conversations")
    op.drop_column("conversations", "last_message_preview")
    op.drop_column("conversations", "last_message_at")
