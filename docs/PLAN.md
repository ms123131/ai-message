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

## Фаза 3 — Реальные данные из Bitrix24 (NEXT)

Цель: чтобы wizard, Inbox и Dashboard показывали **реальные данные с подключённого портала**, а не mock'и.

### 3.1 Bitrix24 коннектор — полноценный
- [ ] `app/integrations/bitrix24/client.py` — REST-клиент с автоматическим обновлением `access_token` по `refresh_token` за 5 минут до истечения
- [ ] Throttling: 2 req/sec на портал (`asyncio.Semaphore` + sleep)
- [ ] Поддержка `batch` для группировки до 50 запросов
- [ ] Обработка ошибок `expired_token` → авто-refresh → retry
- [ ] Поддержка webhook-режима (вызов через сохранённый `webhook_url`)

### 3.2 Подписка на события
- [ ] При создании OAuth-подключения автоматически вызывать `event.bind` для:
  - `OnImOpenLinesMessageAdd` (новое сообщение в Open Channels)
  - `OnImOpenLinesSessionStart` / `OnImOpenLinesSessionFinish`
  - `OnCrmActivityAdd` с `TYPE_ID=EMAIL` (входящие письма через CRM)
- [ ] Endpoint `/webhooks/bitrix24`: валидация `auth[application_token]`, dedup по `event_handler_id`
- [ ] Постановка событий в очередь (на старте — `asyncio.Queue` + воркер в lifespan; позже — Redis/Celery)

### 3.3 Исторический импорт ✅ (MVP)
- [x] Команда `python -m app.cli import-bitrix24 --integration-id <id> --days 30`
- [x] Импорт через `im.recent.get` (ONLY_OPENLINES) + `imopenlines.session.history.get` по CHAT_ID, дедуп через unique-индексы
- [x] Модель `ImportJob` + `POST /api/v1/integrations/{id}/import` (BackgroundTasks) + `GET /import-jobs`
- [ ] TODO: полная история всех закрытых сессий чата (сейчас берём только последнюю, видимую через history.get)
- [ ] TODO: качать вложения с Bitrix Disk (сейчас сохраняем только метаданные)

### 3.4 Модель данных (расширение)
- [ ] `Conversation` (id, integration_id, external_id, channel, contact_name, status, created_at)
- [ ] `Message` (id, conversation_id, external_id, sender_type [client/agent/bot], text, attachments_json, sent_at)
- [ ] Индексы: `(integration_id, created_at desc)`, `(conversation_id, sent_at)`
- [ ] Полнотекстовый поиск Postgres (`tsvector` + GIN)

### 3.5 API для Inbox/Dashboard на реальных данных
- [ ] `GET /api/v1/conversations` — фильтры (channel, integration_id, дата)
- [ ] `GET /api/v1/conversations/{id}/messages`
- [ ] `GET /api/v1/dashboard/stats` — объём, AVG response time

### 3.6 Frontend — переключение с mock на API
- [ ] `apps/web/src/pages/InboxPage.tsx` → TanStack Query на `/conversations`
- [ ] `DashboardPage.tsx` → реальные данные
- [ ] Empty state «подключите Bitrix24» если интеграций нет

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

- [ ] **Шифрование секретов в БД**: `client_secret`, `access_token`, `refresh_token` через Fernet/AES-GCM, ключ из `.env` (`ENCRYPTION_KEY`)
- [ ] **Alembic-миграции** вместо `Base.metadata.create_all` (удалить из lifespan)
- [ ] Rate limiting (slowapi) per-tenant
- [ ] Audit log (кто/когда менял интеграции, читал диалоги)
- [ ] CSP-заголовки в nginx
- [ ] Закрыть порты `5432` и `8000` в production `compose.yml`
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

- [ ] `Base.metadata.create_all` в `lifespan` — заменить на Alembic
- [ ] `client_secret` хранится в БД как plain text — зашифровать (Fernet)
- [ ] Bundle размер web > 500 KB — добавить code-splitting (`manualChunks`)
- [ ] Pydantic warning: миграция `class Config` → `ConfigDict` сделана только в одном месте, проверить остальные
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
