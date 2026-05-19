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

    Два режима:
    - Marketplace (без client_id/secret): клиент сначала ставит наше
      тиражное приложение, потом приходит сюда с доменом. Мы ищем
      готовую запись (создана install-handler'ом) и привязываем к tenant.
    - Local (с client_id/secret): для клиентов с собственным локальным
      приложением в B24. Сохраняем credentials в Integration; токены
      прилетают позже в /install/bitrix24, когда клиент установит/
      переустановит приложение на портале.
    """

    domain: str = Field(min_length=3, max_length=255)
    label: str | None = Field(default=None, max_length=200)
    # Только для режима локального приложения.
    client_id: str | None = Field(default=None, max_length=255)
    client_secret: str | None = Field(default=None, max_length=255)


class Bitrix24ConnectNotInstalled(BaseModel):
    """Возвращается, когда интеграция по домену не найдена."""

    status: Literal["not_installed"] = "not_installed"
    domain: str
    install_instructions_url: str
    message: str
