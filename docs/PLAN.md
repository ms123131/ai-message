# План реализации ai-message

> Документ — единая точка правды по состоянию и приоритетам. Обновляется по мере развития. Если вы продолжаете работу в новой сессии — начните с этого файла.

## Что такое ai-message

SaaS-приложение для анализа коммуникационных каналов компании: чаты Bitrix24 (Open Channels: WhatsApp, Telegram, ВК, виджет сайта), CRM-активности, email, мессенджеры. Приоритетная интеграция — **Bitrix24**.

## Контекст для быстрого онбординга

- **Репозиторий:** https://github.com/ms123131/ai-message
- **Локальный путь (workstation):** `/home/project/ai-message`
- **Ветки:** `main` — production, `dev` — основная разработка, `feature/*` → PR в `dev`
- **CI:** GitHub Actions (`.github/workflows/ci.yml`) — typecheck/build для web, ruff+pytest для api, docker-build образа api
- **Деплой:** `compose.yml` в корне — `docker compose up -d --build`, web на :8080
- **Workflow:** feature-ветка → PR в `dev` → merge → PR `dev → main` → release

## Технологический стек

| Слой | Технологии |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind, TanStack Query, React Router, Recharts, lucide-react |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Pydantic v2, httpx |
| База данных | PostgreSQL 16 (production), SQLite (тесты/локальный dev API без compose) |
| Очереди (план) | Celery + Redis |
| NLP (план) | sentence-transformers, BERTopic, Natasha, transformers |
| Инфраструктура | Docker Compose, nginx, GitHub Actions |

---

## Текущее состояние (фазы 0–2 — DONE)

### Фаза 0 — Скаффолд ✅
- [x] pnpm-монорепо (`apps/`, `packages/`, `docs/`)
- [x] `apps/web`: Vite + React + TS + Tailwind, страницы Login/Dashboard/Inbox/Integrations/Settings
- [x] Подключение к GitHub, ветки `main` + `dev`
- [x] CI: typecheck + build (web), ruff + pytest (api), docker build
- [x] PR template, документация workflow в README

### Фаза 1 — MVP Frontend ✅
- [x] Layout с боковым меню
- [x] Wizard «Подключение Bitrix24» (`/integrations/bitrix24/new`) — OAuth + входящий webhook
- [x] Callback-страница OAuth (`/integrations/bitrix24/callback`)
- [x] Inbox с mock-данными
- [x] Дашборд: объём, время ответа, sentiment (Recharts)

### Фаза 2 — Backend MVP ✅
- [x] `apps/api`: FastAPI + SQLAlchemy 2.0 async
- [x] Endpoints: `/api/v1/health`, `/integrations` (CRUD), `/integrations/bitrix24/oauth` (создаёт черновик + authorize_url), `/integrations/bitrix24/oauth/exchange` (реальный обмен code → access_token через oauth.bitrix24.tech), `/integrations/bitrix24/webhook`, `/webhooks/bitrix24` (приёмник событий — пока логирует)
- [x] Модель `Integration` (kind, mode, токены, scope, expires_at, member_id)
- [x] Pytest (4 теста зелёные) + ruff
- [x] Привязка фронтенда к backend через `lib/api.ts` + TanStack Query
- [x] `docker-compose`: postgres + api + nginx-web
- [x] Production `nginx.conf` со SPA fallback, проксированием `/api` и `/webhooks`, security headers, gzip

---

## Фаза 3 — Реальные данные из Bitrix24 ✅ (с двумя открытыми TODO в 3.3)

Цель: чтобы wizard, Inbox и Dashboard показывали реальные данные. Достигнута.

### 3.1 Bitrix24 коннектор ✅
- [x] REST-клиент `client.py` с авто-refresh `access_token` за 5 минут до истечения
- [x] Throttling 2 req/sec на портал (`asyncio.Semaphore`)
- [x] `batch()` до 50 запросов
- [x] Retry на `expired_token` (один проход после refresh)
- [x] ~~Webhook-режим~~ удалён в фазе 4.5 (тиражное приложение — только OAuth)

### 3.2 Подписка на события — заменена поллингом ✅
Универсальное приложение без своего коннектора не получает `OnImOpenLinesMessageAdd`
от B24. Вместо `event.bind` сделан фоновый поллер `poller.py` (`im.recent.get` +
`imopenlines.session.history.get`). Commit `852dc3b`. Поллер уезжает в worker
в PR #3 (Redis + ARQ).

### 3.3 Исторический импорт ✅ (MVP)
- [x] Команда `python -m app.cli import-bitrix24 --integration-id <id> --days 30`
- [x] Импорт через `im.recent.get` (ONLY_OPENLINES) + `imopenlines.session.history.get` по CHAT_ID, дедуп через unique-индексы
- [x] Модель `ImportJob` + `POST /api/v1/integrations/{id}/import` (BackgroundTasks) + `GET /import-jobs`
- [ ] TODO: полная история всех закрытых сессий чата (сейчас берём только последнюю, видимую через history.get)
- [ ] TODO: качать вложения с Bitrix Disk (сейчас сохраняем только метаданные)

### 3.4 Модель данных ✅
- [x] `Conversation`, `Message` с нужными полями (см. `app/db/models.py`)
- [x] Индексы: `(integration_id, created_at)`, `(conversation_id, sent_at)`,
  `(integration_id, status, updated_at)`, уникальные дедуп-индексы
- [x] FTS по `messages.tsv` (Postgres tsvector + GIN-индекс) в `0001_initial.py`

### 3.5 API для Inbox/Dashboard ✅
- [x] `GET /api/v1/conversations` с фильтрами
- [x] `GET /api/v1/conversations/{id}/messages`
- [x] `GET /api/v1/dashboard/{overview,timeline,by-channel,by-manager,heatmap,sla-breaches,top-contacts,by-line,funnel,portal-users}`

### 3.6 Frontend — на реальных данных ✅
- [x] InboxPage на TanStack Query (`/conversations`)
- [x] DashboardPage с табами на реальных KPI и графиках
- [x] Empty state «подключите Bitrix24»

---

## Фаза 4 — Аутентификация и multi-tenancy ✅

- [x] Модели `Tenant`, `User` (role admin/member). `TenantMembership` пока не вводим — один user = один tenant; расширим, когда понадобятся инвайты.
- [x] JWT HS256 (access 15 мин), refresh в HttpOnly cookie (30 дней)
- [x] `/api/v1/auth/{register,login,refresh,logout,me}`, argon2 для паролей, open registration с авто-tenant
- [x] `tenant_id` на `Integration`, фильтрация в репозиториях через JOIN на интеграции
- [x] Миграция данных в lifespan: осиротевшие интеграции привязываются к первому tenant'у
- [x] Frontend: `AuthProvider` + `ProtectedRoute`, реальные Login/Register, авто-refresh при 401 в `lib/api.ts`, logout в AppLayout
- [ ] TODO: TenantMembership + invites для команд (несколько user'ов в одном tenant'е)
- [ ] TODO: роли manager/agent/viewer (сейчас только admin/member)

---

## Фаза 5 — Безопасность и production-готовность

### Инфраструктурный рефакторинг (Alembic + Fernet + Redis/ARQ)

Связка трёх PR. Делаются последовательно, мержатся в `dev` отдельно.

- [x] **PR #1 — Alembic-миграции** вместо `Base.metadata.create_all` + DDL-патчей
  в lifespan. Done в `dev` (commits `32ae0a7`, `ee30e2a`, `0974750`).
  Реализовано: `alembic.ini`, `migrations/env.py` (async), `0001_initial.py`
  (вся схема), отдельный compose-сервис `migrate` (one-shot), CI прогоняет
  upgrade/downgrade/upgrade против Postgres. Тесты остаются на SQLite +
  `Base.metadata.create_all` через `conftest.py`. Подводные камни на будущее:
  `postgresql.ENUM(create_type=False)` обязателен (sa.Enum игнорирует флаг),
  `.gitattributes` форсирует LF для `*.sh`/`Dockerfile` (Windows-чекаут).
- [x] **PR #2 — Fernet** для шифрования `client_secret`, `access_token`,
  `refresh_token` в `integrations`. Реализовано: `cryptography>=43`,
  `app/security/crypto.py` с `MultiFernet` и поддержкой ротации
  (`ENCRYPTION_KEY=new,old`), `app/security/types.py::EncryptedString`
  TypeDecorator поверх `Text`, alembic-миграция `0003_encrypt_integration_secrets`
  (идемпотентная, downgrade расшифровывает обратно). В `app_env=production`
  отсутствие `ENCRYPTION_KEY` — фатальная ошибка; в dev/test генерируется
  эпhemerал-ключ. Чтение терпимо к plain (`try_decrypt_str`) на случай
  отката миграции. Тесты: `tests/test_crypto.py` — roundtrip, ротация,
  валидация ключа, raw-SQL подтверждение ciphertext в БД.
- [x] **PR #3 — Redis + ARQ**. Воркер фоновых задач вынесен из API-процесса.
  Реализовано: `redis:7-alpine` с AOF в compose, отдельный `worker`-контейнер
  с тем же образом (entrypoint `run-worker` → `arq app.workers.settings.WorkerSettings`),
  `app/workers/{settings,redis_pool,locks,tasks/bitrix_poll,tasks/bitrix_import}.py`.
  Distributed lock per integration через `redis SET NX EX` (TTL=600с).
  Diapatch_poll работает по self-rescheduling-паттерну (`_defer_by`), что
  позволяет произвольный интервал из env, не только делители 60с.
  `POST /integrations/{id}/import` теперь enqueue-ит задачу в Redis вместо
  `BackgroundTasks`. Тесты на fakeredis (без отдельного Redis в CI).
  Старый `poller.py` и asyncio-task в lifespan удалены — катовер чистый.

### Прочее

- [x] Rate limiting (slowapi) per-tenant — `app/security/ratelimit.py`,
  ключ = `tenant:<tid>` для JWT-запросов или `ip:<addr>` для анонимов.
  Лимиты: register 5/min, login 10/min, refresh 30/min, import 6/min.
  В тестах лимитер сбрасывается между запусками через autouse-фикстуру.
- [x] Audit log — `audit_logs` (миграция 0004), `app/security/audit.py`.
  Пишем: integration.delete/connect, auth.login_failed. Запись в той же
  транзакции, что и основное действие.
- [x] CSP-заголовки в nginx — строгий `default-src 'self'` для SPA,
  отдельный `frame-ancestors *.bitrix24.*` для `/install/`, плюс
  `Permissions-Policy`.
- [x] Закрыть порты `5432` и `8000` в production `compose.yml` — публикация
  убрана; для dev-отладки `compose.override.example.yml` (в .gitignore).
- [ ] Pen-test перед коммерческим запуском

---

## Фаза 6 — Анализ (NLP / AI)

Архитектурно делим LLM-задачи на **fast** (массовые: sentiment, тэги) и
**smart** (нюансы: резюме, weekly insights). Каждое назначение —
отдельный провайдер из конфига, можно одинаковый. Локальные NLP-фичи
(NER через Natasha, регулярки) идут без LLM-провайдера вообще.

**Текущий статус подфаз:**

| Подфаза | Статус | Что внутри |
|---|---|---|
| 6.0 LLM-абстракция | ✅ | base/claude/openai_compat/null/factory |
| 6.1 Sentiment | ✅ | Message+Conversation поля, batch worker, dashboard, auto-cron |
| 6.1.1 Sentiment UI | ✅ | бэйджи в Inbox, donut+top-negative, фильтр-чип |
| 6.2 LLM-теги | ✅ | словарь 41 темы, Conversation.tags денормализация, чипы #тема в Inbox |
| 6.3 LLM-резюме | ✅ | smart-LLM, кнопка «Сводка» в Inbox, индикатор устаревания |
| 6.6 Извлечение сущностей | ✅ | 14 типов: phone (RU+intl), email, url, @social, tracking, money, ИНН/ОГРН/КПП/счёт, card (маскир.+Luhn), IBAN, date + Natasha NER (person/loc/org). EntityChips в Inbox |
| 6.5 Эмбеддинги + pgvector | ✅ | sentence-transformers MiniLM-L12 (384d), pgvector ivfflat cosine, GET /conversations/{id}/similar, кнопка «Похожие диалоги» в Inbox |
| 6.4 BERTopic | ⏳ | динамические темы поверх эмбеддингов |
| 6.7 Weekly insights + аномалии + AI Control Panel | ⏳ | smart-LLM, детекторы всплесков, единая страница |

### 6.0 Базовая абстракция LLM-провайдеров ✅
- [x] `app/integrations/llm/{base,claude,openai_compat,null,factory}.py`
- [x] Единый интерфейс `LLMProvider.chat(messages) -> LLMResponse`,
  ошибки маппятся в `LLMError` / `LLMUnavailableError` / `LLMTimeoutError`
- [x] OpenAI-compat провайдер один на всех (Groq, OpenAI, OpenRouter,
  DeepSeek, Together, VseGPT, локальные vLLM) — разница только в base_url
- [x] Anthropic Claude — отдельная реализация через REST (без SDK)
- [x] Null-провайдер — безопасный дефолт, возвращает заглушки без сети
- [x] Конфиг: `LLM_FAST_*` и `LLM_SMART_*` (provider/model/api_key/base_url)
- [x] Тесты с httpx.MockTransport — happy path, 5xx → unavailable,
  4xx → error, timeout, валидация конфига

### 6.1 Sentiment analysis ✅ (MVP)
- [x] Schema: `Message.{sentiment, sentiment_confidence, sentiment_at,
  sentiment_model}`, `Conversation.sentiment_score`. Миграция 0005,
  частичный индекс `ix_messages_sentiment_pending`
- [x] `app/nlp/sentiment.py`: `classify(text)` через fast-LLM с однословным
  промптом и терпимым парсером; `analyze_messages_batch(session, ids)`;
  `recompute_conversation_sentiment_score(session, conv_id)`. Считаем
  только клиентские сообщения (sender_type=client)
- [x] arq-таска `analyze_sentiment_for_integration(integration_id, batch_size)`
  под distributed-локом per-integration
- [x] `POST /integrations/{id}/analyze-sentiment` — enqueue батча
- [x] `GET /dashboard/sentiment` — распределение по тональностям + avg_score
- [x] Тесты: парсер, классификатор (stub + null), пересчёт score,
  endpoint, enqueue в arq
- [x] Авто-cron через `NLP_CRON_INTERVAL_MINUTES` (commit `27f9d79`).
  `nlp_dispatch_cron` раздаёт sentiment+tags+entities на все
  connected-интеграции; arq cron registers только если интервал > 0.

### 6.1.1 Sentiment UI ✅ (commit `e0be859`)

Frontend-вывод тональности на дашборде и в Inbox.

- [x] `ConversationOut.sentiment_score` в API
- [x] `GET /dashboard/top-negative-conversations` (commit `4721f7c`)
- [x] `SentimentBadge` в карточке диалога Inbox + tooltip с описанием
- [x] Фильтр-чип «Только негатив/позитив/нейтрал» в `DashboardFilterBar`
- [x] KPI «Средняя тональность» в Overview-табе с дельтой к прошлому периоду
- [x] AI-таб: donut по buckets + список топ-10 негативных + кнопка
  «Запустить анализ» с polling до результата
- [x] Empty state «подключите LLM-провайдера», баннер на Settings при
  `LLM_FAST_PROVIDER=null`
- [x] Vitest: бэйдж/donut/кнопка

Отложено в 6.7: sentiment-таймлайн по дням, sentiment по операторам,
per-message раскраска в просмотре диалога.

### 6.2 LLM-теги / темы ✅ (commits `27f9d79`, `dacc589`, `4da8b48`)

- [x] `Message.{tags, tags_at, tags_model}` (JSON list 0-3) + миграция
  0007 + частичный индекс `ix_messages_tags_pending`
- [x] `app/nlp/tags.py`: `classify_tags(text, vocab)` через fast-LLM,
  толерантный парсер (запятые/кавычки/пробелы вместо подчёркиваний),
  словарь из `Settings.tags_vocabulary` (env `TAGS_VOCABULARY`)
- [x] Расширенный дефолтный словарь — 41 тема по 7 категориям (деньги/
  заказ/доставка, товар/услуга, техподдержка, жалобы, коммуникации,
  намерения, fallback). Переопределяется через env.
- [x] arq-таска `analyze_tags_for_integration` под локом `kind=tags`,
  фильтр клиентских + Bitrix-служебных текстов
- [x] `POST /api/v1/integrations/{id}/analyze-tags`
- [x] `GET /api/v1/dashboard/tags` — топ-N с count/share, dialect-aware
  (Postgres `jsonb_array_elements` / SQLite Python-итерация)
- [x] AI-таб: TagsBlock с donut + список + кнопка «Запустить тегирование»
  с polling (фикс залипания при pending=0 — commit `1b3ab4a`)
- [x] **Денормализация на уровне Conversation** (`Conversation.tags` +
  миграция 0008): worker после батча пересчитывает теги диалогов через
  `recompute_conversation_tags`. В Inbox под карточкой — чипы `#тема`.

Отложено в 6.4: динамический словарь из топ-N кластеров BERTopic.

### 6.3 LLM-резюме диалогов ✅ (commits `6ab217c`, `96ad1b6`)

- [x] `Conversation.{summary, summary_at, summary_model,
  summary_messages_count}` + миграция 0006
- [x] `app/nlp/summary.py` + worker `summarize_conversation_task` через
  smart-LLM (Claude Haiku/Llama по дефолту)
- [x] `POST /api/v1/conversations/{id}/summarize` с rate-limit 12/min
- [x] UI «Сводка» в Inbox + индикатор устаревания (если новые сообщения
  пришли после `summary_at`)

### 6.4 Topic modeling (BERTopic)
- [ ] Локально на CPU поверх эмбеддингов (см. 6.5). Раз в сутки
  пересчитывает темы и сохраняет в `topic_clusters`. Замена статичного
  словаря 6.2 на динамический.

### 6.5 Эмбеддинги + pgvector ✅

Локальные эмбеддинги без LLM-вызовов — основа для семантического поиска
и BERTopic (6.4).

- [x] Postgres-образ → `pgvector/pgvector:pg16` (compose.yml), миграция
  0010 включает `CREATE EXTENSION vector`, добавляет `messages.embedding`
  типа `vector(384)` + `embedding_at` + `embedding_model`
- [x] `app/db/types.py::EmbeddingVector` — TypeDecorator: `Vector(384)`
  на Postgres, JSON-список на SQLite (тесты)
- [x] Частичный индекс `ix_messages_embedding_pending` (NULL embedding)
  + ivfflat-индекс `ix_messages_embedding_cosine` (lists=100, cosine)
- [x] `app/nlp/embeddings.py` — lazy-init `sentence-transformers/
  paraphrase-multilingual-MiniLM-L12-v2` (~470 МБ), L2-нормализованные
  векторы, gracefully падает в null-режим без пакета
- [x] Worker `embed_messages_for_integration` под локом `kind=embeddings`,
  фильтр client+agent + bitrix-system; `nlp_dispatch_cron` ставит и
  embed-задачу
- [x] `POST /api/v1/integrations/{id}/analyze-embeddings` (rate-limit 6/min)
- [x] `GET /api/v1/conversations/{id}/similar?limit=N` — центроид
  исходного диалога считается в Python, дальше один SQL с `<=>` группой
  по conversation_id (MIN distance), фильтр по tenant. На SQLite —
  `available=False`, graceful-degrade
- [x] UI: `SimilarBlock` в Inbox под карточкой — раскрывающийся список
  с процентом близости, ссылка на похожий диалог
- [x] Тесты (6 кейсов): stub-encoder с детерминированным hash → vector,
  батч+БД (пишет, пропускает уже-эмбедженных, держит pending при
  недоступной модели), эндпоинт enqueue, similar graceful на SQLite,
  cron ставит и embed-таску
- [x] Config: `EMBEDDINGS_MODEL` / `EMBEDDINGS_BATCH_SIZE` /
  `EMBEDDINGS_MAX_CHARS` (Settings)

### 6.6 Извлечение сущностей ✅ (commits `94bf3c9`, `a9d91d1`, `acfef0a`, `1283db7`)

Локальный NER без LLM — Natasha + регулярки. Дешёвый и быстрый сток
контактов, реквизитов и упоминаний.

- [x] `Message.{entities, entities_at}` (JSON) + миграция 0009 +
  частичный индекс `ix_messages_entities_pending`
- [x] `app/nlp/entities.py`. Полная палитра типов:
  - **Контакты:** телефон RU + международные E.164 (нормализация в
    `+XXX...`), email (trailing-пунктуация обрезается), URL,
    `@social_handle` (Telegram-ссылка по клику)
  - **Логистика:** tracking — EMS/UPS/Boxberry (BSP/BB)/СДЭК/DHL/DPD;
    дедупликация с phone/inn/account, чтобы длинные цифры не задваивались
  - **Деньги:** сумма с валютой RUB/USD/EUR/KZT/UAH → `{amount, currency, raw}`
  - **Реквизиты юрлица** (по контекстному хинту): ИНН (10/12),
    ОГРН/ОГРНИП (13/15), КПП (9), расчётный счёт (20)
  - **Платёжные:** банковская карта с Luhn-валидацией —
    маскируется в `**** **** **** XXXX` (полный PAN никогда не
    сохраняется); IBAN (15-34 alphanumeric)
  - **Дата:** DD.MM.YYYY, DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
  - **Natasha NER** (lazy-init, один раз на процесс ~150мб моделей):
    `person` / `location` / `organization`. Опциональна — если пакет
    не установлен, регулярки продолжают работать
- [x] Worker `analyze_entities_for_integration` под локом `kind=entities`.
  Обрабатывает client + agent, исключает system-сообщения Bitrix
  (фикс a9d91d1 — там Natasha матчила служебные слова как мусор)
- [x] `POST /api/v1/integrations/{id}/analyze-entities`
- [x] `nlp_dispatch_cron` теперь ставит и entities-задачу
- [x] `MessageOut.entities` в API
- [x] `EntityChips` в Inbox под bubble (client + agent) — цветные
  кликабельные чипы с иконками lucide-react; phone → `tel:`,
  email → `mailto:`, url → новая вкладка, @social → `t.me/...`;
  деньги форматируются по локали `ru-RU`
- [x] Тесты: 32 кейса (regex unit для всех типов, Luhn, money parser,
  дедупликация bucket'ов, batch+БД, endpoint, natasha stub без
  реальных моделей)

Что НЕ сделано в этой итерации (намеренно):
- Фильтр в Inbox «есть телефон/email/трек» — поле в БД готово, UI-чип
  ~30 мин при необходимости
- Дашборд-блок «топ упомянутых сумм/городов/компаний» — уйдёт в 6.7
- Авто-обогащение CRM Bitrix24 контактами из чата — отдельная фича,
  решить, в какие поля писать
- Полнотекстовый поиск по entities (`messages.entities->>'phone'`) —
  есть GIN-индекс на JSONB по умолчанию, отдельный API эндпоинт
  «найти все диалоги с этим телефоном» — позже

### 6.7 Weekly insights и аномалии
- [ ] smart-провайдер раз в неделю собирает overview + outlier-диалоги
  → presigned-доклад в кабинете
- [ ] Аномалии: всплески объёма, резкие изменения SLA, пики негатива
- [ ] Общий AI Control Panel: одна страница со статусом всех NLP-фич,
  кнопки запуска ручных триггеров (sentiment/tags/entities), графики
  доли проанализированного, последний прогон cron-а

---

## Фаза 7 — Деплой и инфраструктура

- [ ] **Выбрать хостинг**: Yandex Cloud / VK Cloud / self-hosted VPS (Docker Desktop — только для локальной разработки)
- [ ] TLS (Caddy или traefik) перед nginx
- [ ] Бэкапы Postgres в S3-совместимое хранилище (`pg_dump` по cron)
- [ ] Логи: Loki + Grafana или агрегатор провайдера
- [ ] Метрики: Prometheus exporter в FastAPI (`prometheus-fastapi-instrumentator`)
- [ ] Sentry для ошибок FE и BE
- [ ] Доработать `.github/workflows/deploy.yml` под выбранный хостинг (SSH + `docker compose pull/up` или push в GHCR)

---

## Маркетинговый сайт

См. [`docs/SITE_PLAN.md`](./SITE_PLAN.md) — отдельный план под
одностраничный лендинг (одностраничник на корне `/`, текущий SPA
переезжает на `/app`). Контент — хардкод в исходниках, без CMS.

---

## Фаза 8 — Другие каналы

Подробный план интеграции — `docs/PLAN_CONNECTORS.md` (Telegram Bot →
Personal Telegram → WhatsApp Personal + универсальный механизм verify).

- [ ] Email коннектор (IMAP IDLE + Microsoft Graph + Gmail API)
- [ ] Telegram Bot API (прямой коннектор)
- [ ] Personal Telegram (Telethon, QR-логин — основной flow; phone+code — fallback)
- [ ] WhatsApp personal (Wazzup-reseller или Baileys-сайдкар — выбор TBD)
- [ ] amoCRM, HubSpot — после Bitrix24

---

## Фаза 5 — Аналитический дашборд (расширение) ✅

Цель: превратить сводный экран в реальный инструмент аналитики, который
показывает то, чего нет в стандартных отчётах Bitrix24.

### 5А Схема и сборщики
- [x] Расширение `Conversation`: `assigned_user_id`, `line_id`,
  `first_message_at`, `first_agent_reply_at`, `closed_at`, `response_time_sec`
- [x] Индексы: `(integration_id, assigned_user_id)`, `(integration_id, status, updated_at)`
- [x] Новая таблица `PortalUser` (кэш операторов Bitrix24)
- [x] `_recompute_conversation_analytics` в импортере (FRT по фактическим сообщениям)
- [x] `_session_meta` — извлекаем `OPERATOR_ID`/`CONFIG_ID` из session
- [x] `users_sync.py` — `sync_portal_users_if_stale` раз в сутки в поллере

### 5Б Backend API (8 эндпоинтов)
- [x] `GET /dashboard/overview` — KPI с дельтами к прошлому периоду
- [x] `GET /dashboard/timeline` — точки по дням
- [x] `GET /dashboard/by-channel` — donut
- [x] `GET /dashboard/by-manager` — таблица операторов с JOIN PortalUser
- [x] `GET /dashboard/heatmap` — день недели × час
- [x] `GET /dashboard/sla-breaches` — открытые диалоги без ответа > N минут
- [x] `GET /dashboard/top-contacts` — топ контактов
- [x] `GET /dashboard/portal-users` — справочник операторов
- [x] Унифицированные фильтры: `days`, `integration_id`, `channel`, `operator_id`
- [x] Алиас старого `/stats` сохранён для обратной совместимости

### 5В Frontend
- [x] `DashboardPage` с табами «Обзор / Менеджеры / Контакты / AI»
- [x] `DashboardFilterBar` — период/портал/канал/оператор
- [x] `KPICard` с дельтой ±% (зелёный/красный с учётом higherIsBetter)
- [x] Overview: 8 KPI, area-chart, donut, heatmap, SLA-список
- [x] Managers: bar chart FRT топ-10 + таблица всех операторов с аватарами
- [x] Contacts: топ-30 с количеством диалогов и сообщений

### 5Г AI-таб (заглушки «скоро»)
- [x] Hero-блок с описанием будущего раздела
- [x] 8 lock-карточек: sentiment, темы, аномалии, quality score,
  авто-резюме, churn risk, авто-теги, weekly insights
- [x] Превью-визуализации для каждой карточки
- [x] Реальная NLP — отложена в фазу 6

## Фаза 4.5 — Wazzup-style подключение Bitrix24 ✅

Цель: клиент НЕ вписывает client_id/secret вручную. Ставит наше тиражное
приложение → возвращается в наш UI → вводит домен → готово.

- [x] Глобальные `BITRIX24_APP_CLIENT_ID/SECRET` в `.env` (одно приложение
  на всех клиентов)
- [x] `/install/bitrix24` принимает POST от B24, сохраняет токены в Integration
  (tenant_id=NULL — pending claim), вызывает `BX24.installFinish()` в iframe
- [x] `POST /integrations/bitrix24/connect` (domain, label?) — находит pending
  Integration по домену и привязывает к tenant. 404 с `status: not_installed`
  если приложение не установлено. 409 если уже привязано к другому tenant.
- [x] Удалён webhook-режим интеграции: модель, endpoint, UI, тесты (приёмник
  событий `/webhooks/bitrix24` остался)
- [x] Bitrix24Wizard упрощён: только домен + инструкция «поставьте приложение»
- [x] Favicon SVG
- [ ] TODO: вынести client_id/secret в таблицу Bitrix24App при появлении
  нескольких приложений (.ru/.com или разные тарифы)

## Фаза 3.4 — Надёжность интеграции с Bitrix24 ✅ (2026-05-20)

Боевая отладка по живому порталу выявила цепочку дефектов, из-за которых
дашборд показывал «Со сделкой 0» при наличии сделок в B24. Все исправлены
и запушены в `dev`.

- [x] **Bitrix REST: сериализация вложенных dict/list в PHP-стиль.** Главный
  скрытый баг: `urllib.parse.urlencode` сериализовал `{"filter": {...}}`
  через `repr()` → Bitrix падал с `"Parameter 'order' must be array"`.
  Ошибки проглатывались `try/except` в `enrich_entities`/`sync_stages_cache`,
  поэтому проявлялись как «всё работает, но crm_entities пустые».
  `_flatten_params` рекурсивно раскладывает в `filter[>=DATE_CREATE]=...`,
  `filter[@ID][0]=1` (commit `ff5d14e`).
- [x] **OAuth: статус интеграции при провале refresh.** `_refresh` делал
  `flush` без `commit`; вызывающий код закрывал сессию по rollback →
  status откатывался, UI/БД врали `connected` при мёртвом refresh-токене.
  Теперь `commit` при `BitrixOAuthError` (commit `23335b2`).
- [x] **Обратный CRM-индекс.** На части порталов B24 не отдаёт блок
  `session` в `imopenlines.session.history.get` — наш парсер `session.crm`
  никогда не находил привязок. Прямого «по chat_id → сделка» в API нет,
  только обратный путь. Воркер `dispatch_crm_sync` теперь пробегает
  `crm.deal.list`/`crm.lead.list` за окно (`BITRIX24_CRM_LINK_WINDOW_DAYS`,
  default 30 дней), батчем по 50 дёргает `imopenlines.crm.chat.get` и
  связывает найденные CHAT_ID с уже импортированными `Conversation`
  (commit `d321d35`).
- [x] **CRM-enrich на webhook.** `OnOpenLineMessageAdd` создавал
  Conversation+Message без CRM-привязки; даже после починки поллера
  свежие диалоги жили без сделок до следующего цикла поллера. Теперь
  webhook ставит arq-задачу `enrich_conversation_from_chat`, которая
  дотягивает session.history для одного chat_id, обновляет
  operator/line/contact и создаёт CrmEntity+ConversationCrmLink
  (commit `23335b2`).
- [x] **Бэкфил ConversationCrmLink.** `POST /integrations/{id}/enrich-conversations`
  и CLI `python -m app.cli crm-link` — разовый прогон по существующим
  диалогам после первого подключения или починки.
- [x] **CLI: `debug-history`.** Команда показывает, какие ключи Bitrix
  возвращает в `imopenlines.session.history.get` и что вытаскивает
  парсер. Полезна, когда «Со сделкой 0» — за минуту видно, дело в
  отсутствии session-блока, в кривых полях, или в нашем коде.
- [x] **Nginx: динамический resolver.** После `docker compose up --build api`
  контейнер api получал новый IP, nginx кэшировал старый навсегда → web
  отдавал Bad Gateway до собственного рестарта. Добавлен
  `resolver 127.0.0.11 valid=10s` + `proxy_pass` через переменную; web
  ждёт api `service_healthy` (commit `4e93159`).

**Контекст**: см. транскрипт сессии 2026-05-20 — там показан полный
follow-the-data путь от «funnel показывает 0» через invalid_grant,
пустой `session.crm`, до `urlencode` ломающего весь CRM-сток.

---

## Известные технические долги

- [x] ~~`Base.metadata.create_all` в `lifespan` — заменить на Alembic~~ (PR #1)
- [x] ~~`client_secret` хранится в БД как plain text — зашифровать (Fernet)~~ (PR #2)
- [ ] Bundle размер web > 500 KB — добавить code-splitting (`manualChunks`)
- [x] ~~Pydantic warning: миграция `class Config` → `ConfigDict`~~ — проверено,
  старого синтаксиса в коде нет; все BaseModel либо без конфига, либо на
  `ConfigDict(from_attributes=True)`, Settings на `SettingsConfigDict`
- [ ] CI на feature-ветках не запускается (только PR/push в main/dev) — норма для GitHub Flow, но если хотите CI на любой push — добавить `branches: ['**']`

---

## Быстрый старт (для новой сессии)

### Локальная разработка

```bash
cd /home/project/ai-message

# Backend
cd apps/api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000
# Swagger: http://localhost:8000/docs

# Frontend (в другом терминале)
cd /home/project/ai-message
pnpm install
cp apps/web/.env.example apps/web/.env
pnpm --filter @ai-message/web dev
# http://localhost:5173
```

### Полный стек через Docker

```bash
cd /home/project/ai-message
cp .env.example .env  # ОБЯЗАТЕЛЬНО: задать POSTGRES_PASSWORD, JWT_SECRET
docker compose up -d --build
# http://localhost:8080
```

**Важно про миграции:** сервис `migrate` запускается one-shot и завершается.
После обновления кода нужно пересобрать ВСЕ образы, включая `migrate`,
иначе alembic не увидит новых ревизий. Самый надёжный путь:

```bash
docker compose build         # пересобрать всё
docker compose run --rm migrate   # явно прогнать миграции
docker compose up -d         # поднять стек
```

Проверить, что миграция применилась:
```bash
docker compose exec postgres psql -U aimessage -d aimessage \
  -c "SELECT version_num FROM alembic_version;"
```

### NLP / AI фичи в проде

```bash
# Включить авто-cron sentiment+tags+entities
echo "NLP_CRON_INTERVAL_MINUTES=10" >> .env
docker compose up -d --force-recreate worker

# Ручной триггер по интеграции (sentiment/tags = fast-LLM, entities = locally)
curl -X POST http://localhost:8080/api/v1/integrations/<id>/analyze-sentiment
curl -X POST http://localhost:8080/api/v1/integrations/<id>/analyze-tags
curl -X POST http://localhost:8080/api/v1/integrations/<id>/analyze-entities

# Сводка диалога (smart-LLM)
curl -X POST http://localhost:8080/api/v1/conversations/<id>/summarize
```

Для tags/sentiment нужен `LLM_FAST_API_KEY`; для summary — `LLM_SMART_API_KEY`.
Entities (Natasha + regex) работают без LLM-ключей.

### Git workflow

```bash
git checkout dev && git pull
git checkout -b feature/short-desc
# ...работа...
git push -u origin feature/short-desc
gh pr create --base dev  # или через GitHub UI
```

---

## Соглашения

- **Commit messages:** Conventional Commits (`feat:`, `fix:`, `chore:`, `build:`, `ci:`, `docs:`, `refactor:`)
- **Branch naming:** `feature/<short-desc>`, `fix/<short-desc>`, `chore/<short-desc>`
- **PR:** заголовок ≤70 символов, в body — Summary + Test plan
- **Без секретов в коммитах** — всё через `.env` (в `.gitignore`)
- **Frontend:** компоненты в `src/components/`, страницы в `src/pages/`, API-клиент в `src/lib/api.ts`
- **Backend:** routers в `app/api/v1/`, модели в `app/db/models.py`, схемы в `app/schemas/`, коннекторы в `app/integrations/<name>/`

---

## Подтверждение email (на выбор перед стартом)

Сейчас регистрация открыта без верификации почты. Перед коммерческим
запуском нужно закрыть, чтобы нельзя было занимать чужие адреса и чтобы
работали инвайты/восстановление пароля. Три рабочих варианта:

### Вариант 1 — Hard-confirm (как у Gmail/Notion)
Блокируем `/auth/login` до клика по ссылке из письма.
- Поле `User.email_verified_at` (nullable) + таблица
  `email_verification_tokens (token, user_id, expires_at, used_at)`
- `/auth/register` создаёт пользователя, шлёт письмо, **не** возвращает
  access_token (либо возвращает `{requires_verification: true}`)
- `/auth/verify?token=...` → выставляет `email_verified_at`, удаляет токен
- `/auth/resend-verification` (rate-limit 1/мин)
- Плюс: чистая база, нельзя занять чужой email
- Минус: лишний клик перед первым входом

### Вариант 2 — Soft-confirm (рекомендую)
Пускаем в продукт сразу, но баннер «подтвердите почту» + блокируем
чувствительные действия (инвайты в tenant, смена email, экспорт).
- Те же поля и токены, но `/auth/register` сразу выдаёт access_token
- Декоратор `@requires_verified` на конкретных эндпоинтах
- Плюс: лучший онбординг, не ломает текущий flow
- Минус: чуть больше кода в enforcement

### Вариант 3 — Magic-link вместо пароля
Убираем пароли: email → ссылка → залогинен. Сам логин == подтверждение.
- Плюс: проще auth-код (нет argon2, нет «forgot password»)
- Минус: серьёзная перестройка работающего JWT/argon2 flow

### Провайдер для писем
Без этого ни один вариант не взлетит.

| Провайдер | Setup | Цена |
|---|---|---|
| **SMTP через Yandex 360 / Mail.ru для бизнеса** | env + `aiosmtplib`, DKIM из коробки | бесплатно при корпоративной почте |
| Resend / Postmark / SendGrid | API-ключ, шаблоны, дашборд доставляемости | trial → $20/мес |
| Свой Postfix | DKIM/SPF/DMARC, репутация IP | дорого по времени |

**Решение к моменту реализации:** TBD (вариант + провайдер).
План реализации (HTML-шаблон, миграция, тесты) распишется после выбора.
