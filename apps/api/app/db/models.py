from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DDL,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    func,
)
from sqlalchemy import JSON as SAJSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Tenant(Base):
    """Изолированное пространство данных (организация-клиент)."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserRole(str, Enum):
    admin = "admin"
    member = "member"


class User(Base):
    """Пользователь приложения, привязан к одному tenant'у."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        default=UserRole.member,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")


class IntegrationKind(str, Enum):
    bitrix24 = "bitrix24"


class IntegrationMode(str, Enum):
    oauth = "oauth"


class IntegrationStatus(str, Enum):
    pending = "pending"
    connected = "connected"
    error = "error"


class Integration(Base):
    """Одно подключение к внешней системе (Bitrix24 портал, IMAP-ящик и т.д.)."""

    __tablename__ = "integrations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,  # nullable для миграции существующих записей
        index=True,
    )
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="integration",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ConversationChannel(str, Enum):
    """Канал, из которого пришёл диалог."""

    # Bitrix24 Open Channels: каждый коннектор — отдельное значение.
    whatsapp = "whatsapp"
    telegram = "telegram"
    vk = "vk"
    instagram = "instagram"
    facebook = "facebook"
    livechat = "livechat"  # виджет сайта
    email = "email"
    other = "other"


class ConversationStatus(str, Enum):
    open = "open"
    closed = "closed"


class SenderType(str, Enum):
    client = "client"
    agent = "agent"
    bot = "bot"
    system = "system"


class Conversation(Base):
    """Один диалог (Open Channels session, email-цепочка и т.п.)."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    integration_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Идентификатор на стороне внешней системы (Bitrix CHAT_ID, session_id и т.д.).
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[ConversationChannel] = mapped_column(
        SAEnum(ConversationChannel, name="conversation_channel"),
        nullable=False,
    )
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_external_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus, name="conversation_status"),
        default=ConversationStatus.open,
        nullable=False,
    )

    # Закреплённый оператор открытой линии (Bitrix24 OPERATOR_ID).
    # Хранится как строка — Bitrix отдаёт числовой id, но в других каналах
    # будет email/handle. Связь с PortalUser по (integration_id, external_id).
    assigned_user_id: Mapped[str | None] = mapped_column(String(128))
    # ID открытой линии (для разреза «по линиям» в аналитике).
    line_id: Mapped[str | None] = mapped_column(String(64))

    # Денормализованные таймстемпы для быстрой аналитики (FRT, AHT, объём).
    # Заполняются импортером и поллером, индекс — на created_at уже есть.
    first_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_agent_reply_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # First Response Time в секундах = first_agent_reply_at - first_message_at.
    # Денормализован, чтобы AVG/PERCENTILE-запросы не считали разность каждый раз.
    response_time_sec: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    integration: Mapped["Integration"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.sent_at",
    )

    __table_args__ = (
        # Список диалогов на портале по дате — главный запрос Inbox.
        Index(
            "ix_conversations_integration_created",
            "integration_id",
            "created_at",
        ),
        # Дашборд by-manager: фильтр по integration + assigned_user.
        Index(
            "ix_conversations_integration_assigned",
            "integration_id",
            "assigned_user_id",
        ),
        # Дашборд SLA: «активные диалоги без ответа» — статус + last_message.
        Index(
            "ix_conversations_integration_status_updated",
            "integration_id",
            "status",
            "updated_at",
        ),
        # Дедупликация при импорте: один external_id на интеграцию.
        Index(
            "uq_conversations_integration_external",
            "integration_id",
            "external_id",
            unique=True,
        ),
    )


class Message(Base):
    """Одно сообщение в диалоге."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Идентификатор на стороне внешней системы — нужен для дедупликации.
    external_id: Mapped[str | None] = mapped_column(String(128))
    sender_type: Mapped[SenderType] = mapped_column(
        SAEnum(SenderType, name="message_sender_type"),
        nullable=False,
    )
    sender_external_id: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str | None] = mapped_column(Text)
    # Список вложений в произвольной структуре (url, name, mime, size, ...).
    attachments: Mapped[list[dict[str, Any]] | None] = mapped_column(SAJSON)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conversation_sent", "conversation_id", "sent_at"),
        Index(
            "uq_messages_conversation_external",
            "conversation_id",
            "external_id",
            unique=True,
            postgresql_where=sql_text("external_id IS NOT NULL"),
            sqlite_where=sql_text("external_id IS NOT NULL"),
        ),
    )


class PortalUser(Base):
    """Кэш сотрудников портала Bitrix24 (операторов открытых линий).

    Заполняется фоновой синхронизацией через `user.get`. Используется
    в дашборде для отображения имени/аватара по `Conversation.assigned_user_id`
    и `Message.sender_external_id` без обращения к Bitrix24 на каждый рендер.
    """

    __tablename__ = "portal_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    integration_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Идентификатор пользователя в Bitrix24 (числовой, но храним строкой).
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    work_position: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_portal_users_integration_external",
            "integration_id",
            "external_id",
            unique=True,
        ),
    )


class SLATarget(Base):
    """Настройка SLA-таргета на уровне tenant (опционально per channel).

    Если `channel` пуст → таргет действует на все каналы.
    Если задан channel → переопределяет дефолт для этого канала.
    Используется в `/dashboard/sla-breaches` для расчёта «горящих» диалогов.
    """

    __tablename__ = "sla_targets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Если NULL — таргет общий (дефолт для всех каналов).
    channel: Mapped[ConversationChannel | None] = mapped_column(
        SAEnum(ConversationChannel, name="conversation_channel"),
    )
    threshold_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_sla_targets_tenant_channel",
            "tenant_id",
            "channel",
            unique=True,
        ),
    )


class PortalLine(Base):
    """Кэш открытых линий Bitrix24 (line_id → название).

    Заполняется фоновой синхронизацией через `imopenlines.config.list.get`.
    Используется в дашборде («Топ линий») чтобы показывать имена вместо id.
    """

    __tablename__ = "portal_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    integration_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # ID открытой линии в Bitrix24 (CONFIG_ID).
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_portal_lines_integration_external",
            "integration_id",
            "external_id",
            unique=True,
        ),
    )


class ImportJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class ImportJob(Base):
    """Прогресс исторического импорта диалогов из внешней системы."""

    __tablename__ = "import_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    integration_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ImportJobStatus] = mapped_column(
        SAEnum(ImportJobStatus, name="import_job_status"),
        default=ImportJobStatus.pending,
        nullable=False,
    )
    days: Mapped[int] = mapped_column(default=30, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_sessions: Mapped[int] = mapped_column(default=0, nullable=False)
    processed_messages: Mapped[int] = mapped_column(default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_import_jobs_integration_created", "integration_id", "created_at"),
    )


# Полнотекстовый поиск по сообщениям — только Postgres.
# Подключаем generated-колонку `tsv` и GIN-индекс через DDL-хук, чтобы
# SQLite в тестах работал без TSVECTOR.
_FTS_LANG = "russian"


@event.listens_for(Message.__table__, "after_create")
def _create_messages_fts(target, connection, **kw) -> None:  # pragma: no cover
    if connection.dialect.name != "postgresql":
        return
    connection.execute(
        DDL(
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS tsv tsvector "
            f"GENERATED ALWAYS AS (to_tsvector('{_FTS_LANG}', coalesce(text, ''))) STORED"
        )
    )
    connection.execute(
        DDL("CREATE INDEX IF NOT EXISTS ix_messages_tsv ON messages USING GIN (tsv)")
    )
