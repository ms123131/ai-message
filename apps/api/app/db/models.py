from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class IntegrationKind(str, Enum):
    bitrix24 = "bitrix24"


class IntegrationMode(str, Enum):
    oauth = "oauth"
    webhook = "webhook"


class IntegrationStatus(str, Enum):
    pending = "pending"
    connected = "connected"
    error = "error"


class Integration(Base):
    """Одно подключение к внешней системе (Bitrix24 портал, IMAP-ящик и т.д.)."""

    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[IntegrationKind] = mapped_column(
        SAEnum(IntegrationKind, name="integration_kind"),
        nullable=False,
    )
    mode: Mapped[IntegrationMode] = mapped_column(
        SAEnum(IntegrationMode, name="integration_mode"),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[IntegrationStatus] = mapped_column(
        SAEnum(IntegrationStatus, name="integration_status"),
        default=IntegrationStatus.pending,
        nullable=False,
    )

    # OAuth-параметры
    client_id: Mapped[str | None] = mapped_column(String(255))
    # ВАЖНО: client_secret в production должен шифроваться (Vault/KMS).
    # На этапе MVP храним как есть, но не возвращаем в API-ответах.
    client_secret: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    member_id: Mapped[str | None] = mapped_column(String(100))
    scope: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Webhook-режим
    webhook_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
