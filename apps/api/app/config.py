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

    # Fernet-ключ для шифрования секретов в БД (client_secret, access/refresh
    # токены интеграций). Один ключ или несколько через запятую: первый —
    # активный (им шифруем), остальные — для расшифровки старых записей при
    # ротации (см. MultiFernet). В production обязателен, в dev/test при
    # отсутствии генерируется эпhemerал-ключ.
    encryption_key: str | None = Field(default=None)

    bitrix24_oauth_token_url: str = "https://oauth.bitrix24.tech/oauth/token/"
    # Глобальные client_id/secret НАШЕГО Bitrix24-приложения. Хранятся в .env,
    # один на всех клиентов. Клиент устанавливает приложение на свой портал —
    # B24 присылает токены в /install/bitrix24, мы сохраняем их и потом
    # привязываем к tenant'у по доменному имени портала.
    bitrix24_app_client_id: str | None = Field(default=None)
    bitrix24_app_client_secret: str | None = Field(default=None)

    # Публичный URL приложения — используется как handler для event.bind.
    # Например, https://example.com или https://abc123.ngrok-free.app.
    # В compose web проксирует /webhooks/ → api:8000/api/v1/webhooks/.
    webhook_base_url: str | None = Field(default=None)

    # Поллинг Bitrix24 Open Channels. Bitrix не доставляет OnOpenLineMessageAdd
    # приложениям без зарегистрированного коннектора, поэтому подтягиваем
    # сообщения периодическим вызовом im.recent.get → imopenlines.session.history.get.
    # 0 — отключить поллер.
    bitrix24_poll_interval_sec: int = 30
    bitrix24_poll_window_days: int = 1
    # Отдельный дельта-sync статусов сделок/лидов в CRM (без активности диалогов).
    # Bitrix24 не присылает изменения сделок через Open Channels — если у
    # клиента нет новых сообщений, статус won/lost в нашей БД останется
    # устаревшим. Раз в этот интервал воркер дотягивает все известные
    # CrmEntity интеграции. 0 — отключить.
    bitrix24_crm_sync_interval_sec: int = 300
    # Окно (в днях) для обратного CRM-индекса: воркер пробегает свежие
    # сделки/лиды и через `imopenlines.crm.chat.get` находит привязанные
    # чаты. Bitrix24 не отдаёт CRM в imopenlines.session.history.get, и
    # это единственный надёжный способ связать диалог со сделкой.
    bitrix24_crm_link_window_days: int = 30
    # Максимум сделок/лидов, обрабатываемых за один проход индекса (защита
    # от 100k+ сущностей при первом подключении). 0 — без ограничения.
    bitrix24_crm_link_max_entities: int = 1000

    # LLM-провайдеры. Делим на «fast» (массовые дешёвые задачи: sentiment,
    # тэгирование) и «smart» (нюансы: резюме диалогов, weekly insights).
    # Каждый описывается тройкой <provider, model, api_key> + опциональный
    # base_url для openai-compat endpoints (Groq, OpenRouter, DeepSeek, ...).
    #
    # provider ∈ {null, claude, openai, groq, openrouter, deepseek, together, openai_compat}
    # Для openai_compat обязателен LLM_*_BASE_URL.
    #
    # Дефолты — null/null: без ключей ничего не зовётся, фичи возвращают
    # заглушки. Это безопасно: забыл выставить ключ в проде — не упадёт.
    llm_fast_provider: str = "null"
    llm_fast_model: str | None = Field(default=None)
    llm_fast_api_key: str | None = Field(default=None)
    llm_fast_base_url: str | None = Field(default=None)

    llm_smart_provider: str = "null"
    llm_smart_model: str | None = Field(default=None)
    llm_smart_api_key: str | None = Field(default=None)
    llm_smart_base_url: str | None = Field(default=None)

    # Redis (брокер задач для arq-воркера). По умолчанию указывает на
    # compose-сервис `redis`. Для локального dev без docker — `redis://localhost:6379/0`.
    # В тестах подменяется на fakeredis через monkeypatch фабрики пула.
    redis_url: str = "redis://redis:6379/0"
    # TTL distributed-лока на портал при поллинге/импорте. Должен быть больше
    # типичного времени одного прохода с запасом, чтобы лок не отпустился во
    # время работы и не пустил параллельный заход.
    worker_portal_lock_ttl_sec: int = 600

    # Таймзона для отображения временных метрик на дашборде (heatmap день/час).
    # БД хранит timestamptz в UTC, но клиенту нужен «час, когда клиент написал
    # по локальному времени», а не UTC-час. Имя зоны передаётся в Postgres
    # `AT TIME ZONE`, поэтому формат — IANA tz-id (Europe/Moscow, UTC, ...).
    dashboard_tz: str = "Europe/Moscow"

    # Флаг Secure для refresh-cookie. На HTTPS-площадке должен быть True
    # (Chrome/Safari отбрасывают/не шлют Lax-cookie без Secure при
    # некоторых сценариях кросс-доменного редиректа cloudpub-туннеля).
    # Локально на HTTP оставляем False, иначе браузер cookie не сохранит.
    refresh_cookie_secure: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
