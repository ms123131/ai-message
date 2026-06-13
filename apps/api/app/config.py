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

    # Словарь тем для авто-тегирования сообщений (фаза 6.2). Comma-separated
    # slugs на русском. Меняется без редеплоя через env. Динамическое
    # обновление из топ-N кластеров (BERTopic, фаза 6.4) — позже.
    tags_vocabulary: str = (
        # Деньги/заказ/доставка (возврат_средств покрывает "счёт"-возвраты;
        # отдельные "счёт" и "счёт_на_оплату" слиты в один документный тег ниже).
        "оплата,скидка,рассрочка,возврат_средств,"
        "доставка,статус_заказа,адрес_доставки,срок_доставки,"
        "отмена_заказа,изменение_заказа,обмен_товара,"
        # Товар
        "вопрос_о_товаре,наличие,характеристики,подбор_товара,комплектация,"
        # Качество товара
        "брак,гарантия,ремонт,инструкция,"
        # Технические (объединили "не_работает"/"ошибка_сайта"/"ошибка_приложения"
        # в один "техническая_проблема", иначе модель размазывает предикт по синонимам)
        "техническая_проблема,доступ_в_личный_кабинет,смена_пароля,регистрация,"
        # Жалобы (claim покрывает претензию)
        "жалоба,качество_обслуживания,срыв_сроков,"
        # Документы и продажи
        "запрос_документов,договор,коммерческое_предложение,счёт_на_оплату,"
        "обратный_звонок,связаться_с_менеджером,график_работы,"
        # Намерения
        "хочу_купить,консультация,партнёрство,вакансия"
        # Убраны: "спасибо", "приветствие", "другое" — шумовые катч-олл теги,
        # под них модель прицепляла любые короткие/непонятные реплики
        # ("ладно, до свидания" → ["спасибо","приветствие"]). Для дашборда
        # "о чём пишут" они бесполезны. Если ни одна тема не подходит — `none`.
    )

    # Cron-интервал авто-анализа sentiment/tags/entities/embeddings (фаза 6.1).
    # Воркер каждые N минут проходит по connected-интеграциям и ставит
    # батч-задачи. 5 мин — компромисс: дашборд обновляется почти в реальном
    # времени, но fast-LLM не захлёбывается на больших порталах.
    # 0 = отключено (ручной триггер). Минимум 1.
    # Реалтайм-триггер на новые сообщения добавлен в webhooks.py — cron
    # остаётся как safety net для пропущенных и для холодных интеграций.
    nlp_cron_interval_minutes: int = 5
    nlp_cron_batch_size: int = 200

    # Эмбеддинги (фаза 6.5). Модель из sentence-transformers, размерность
    # фиксирована в pgvector-колонке (384). При смене модели на другую с
    # такой же размерностью embedding_model в БД позволит отследить
    # вектора, требующие пересчёта.
    embeddings_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embeddings_batch_size: int = 64
    # Лимит на длину текста для эмбеддинга (символов). Модель режет до
    # 128 токенов сама; ограничение здесь — против гигантских пасторалей.
    embeddings_max_chars: int = 2000

    # Redis-кэш дашборда (фаза 7 — оптимизация). Аналитические эндпоинты
    # `/dashboard/*` считают агрегаты на лету; на больших порталах это
    # 0.5-2с. Большинство клиентов обновляет страницу не чаще раза в
    # минуту, поэтому 60с TTL практически не влияет на воспринимаемую
    # «свежесть», но снимает значительную часть нагрузки с БД.
    # 0 = отключить (так делает test-окружение через env).
    dashboard_cache_ttl_sec: int = 60

    # Personal Telegram (MTProto, Telethon). api_id/api_hash выдаёт
    # https://my.telegram.org per-app — одна пара на всё приложение,
    # привязка к телефону пользователя происходит уже при логине.
    # Без значений endpoint'ы /integrations/telegram-user/* отвечают 503.
    telegram_api_id: int | None = Field(default=None)
    telegram_api_hash: str | None = Field(default=None)
    # TTL контекста QR-логина в секундах. Сам QR-токен Telegram живёт ~30с,
    # но Telethon-объект может пересоздавать его через qr.recreate(); TTL
    # ограничивает суммарное время попыток.
    telegram_qr_ttl_sec: int = 300

    # --- Транзакционная почта (SMTP) ---
    # Отправка писем подтверждения email и сброса пароля. Транспорт —
    # провайдер-агностичный SMTP (Яндекс/ESP), приложение знает только креды.
    # Если smtp_host пуст — отправка отключена (письма логируются и
    # пропускаются), API/регистрация продолжают работать. Это безопасный
    # дефолт для dev/test, аналогично null-режиму LLM.
    smtp_host: str | None = Field(default=None)
    smtp_port: int = 465
    # ssl — неявный TLS (порт 465); starttls — апгрейд на 587; none — без TLS.
    smtp_tls_mode: str = "ssl"
    smtp_user: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    # Адрес и имя отправителя. Если email_from пуст — берём smtp_user.
    email_from: str | None = Field(default=None)
    email_from_name: str = "ai-message"
    # Базовый URL фронтенда — из него строятся ссылки verify/reset в письмах.
    # В проде https://app.77ais.ru, локально — Vite dev-сервер.
    app_base_url: str = "http://localhost:5173"
    # TTL одноразовых токенов из письма.
    email_verify_ttl_hours: int = 24
    email_reset_ttl_hours: int = 2

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
