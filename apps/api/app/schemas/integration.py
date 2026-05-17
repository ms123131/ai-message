from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.db.models import IntegrationMode, IntegrationStatus


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: Literal["bitrix24"]
    mode: IntegrationMode
    label: str
    domain: str
    status: IntegrationStatus
    member_id: str | None = None
    scope: str | None = None
    created_at: datetime
    updated_at: datetime


class Bitrix24OAuthCreate(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    domain: str = Field(min_length=3, max_length=255)
    client_id: str = Field(min_length=5, max_length=255)
    client_secret: str = Field(min_length=5, max_length=255)


class Bitrix24WebhookCreate(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    webhook_url: HttpUrl


class OAuthExchange(BaseModel):
    """Параметры из callback URL после авторизации на портале."""

    integration_id: str
    code: str = Field(min_length=10, max_length=255)
    domain: str
    member_id: str | None = None
    scope: str | None = None


class IntegrationCreated(BaseModel):
    integration: IntegrationOut
    authorize_url: str | None = None
