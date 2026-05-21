from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import ConversationChannel, ConversationStatus, SenderType


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    external_id: str | None = None
    sender_type: SenderType
    sender_external_id: str | None = None
    text: str | None = None
    attachments: list[dict] | None = None
    sent_at: datetime
    tags: list[str] | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    integration_id: str
    external_id: str
    channel: ConversationChannel
    contact_name: str | None = None
    contact_external_id: str | None = None
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime
    sentiment_score: float | None = None
    tags: list[str] | None = None
    summary: str | None = None
    summary_at: datetime | None = None
    summary_model: str | None = None
    summary_messages_count: int | None = None


class ConversationListItem(ConversationOut):
    """Конверсейшн в списке + краткая статистика."""

    message_count: int = 0
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
