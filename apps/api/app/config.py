from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/ai-message.db"
    cors_origins: str = "http://localhost:5173"

    jwt_secret: str = "change-me-in-production"
    jwt_expires_min: int = 60

    bitrix24_oauth_token_url: str = "https://oauth.bitrix24.tech/oauth/token/"
    # client_secret per-tenant — хранится в БД (Integration.client_secret).
    # Глобальный secret оставлен опциональным для одно-арендных установок.
    bitrix24_client_secret: str | None = Field(default=None)

    # Публичный URL приложения — используется как handler для event.bind.
    # Например, https://example.com или https://abc123.ngrok-free.app.
    # В compose web проксирует /webhooks/ → api:8000/api/v1/webhooks/.
    webhook_base_url: str | None = Field(default=None)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
