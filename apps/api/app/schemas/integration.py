from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class Bitrix24ConnectRequest(BaseModel):
    """
    Подключение портала по доменному имени.

    Клиент сначала устанавливает наше приложение в Bitrix24, затем
    приходит сюда и сообщает доменное имя своего портала. Мы ищем
    готовую интеграцию (с уже сохранёнными токенами от install-handler)
    по domain и закрепляем её за tenant'ом пользователя.
    """

    domain: str = Field(min_length=3, max_length=255)
    label: str | None = Field(default=None, max_length=200)


class Bitrix24ConnectNotInstalled(BaseModel):
    """Возвращается, когда интеграция по домену не найдена."""

    status: Literal["not_installed"] = "not_installed"
    domain: str
    install_instructions_url: str
    message: str
