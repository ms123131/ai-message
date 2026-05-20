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

## Фаза 6 — Анализ (NLP)

- [ ] Sentiment analysis (`blanchefort/rubert-base-cased-sentiment-rusentiment`)
- [ ] Извлечение сущностей (Natasha для русского)
- [ ] Topic modeling (BERTopic)
- [ ] Метрики разговоров: First Response Time, Resolution Time, длина
- [ ] Эмбеддинги + pgvector для семантического поиска
- [ ] LLM-суммаризация длинных диалогов (через Claude API)

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

## Фаза 8 — Другие каналы

- [ ] Email коннектор (IMAP IDLE + Microsoft Graph + Gmail API)
- [ ] Telegram Bot API (прямой коннектор)
- [ ] WhatsApp Cloud API (Meta)
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
