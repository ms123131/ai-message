# План реализации ai-message

Полный план — см. согласованный документ в чате. Этот файл служит «живой» проектной памятью и обновляется по мере развития.

## Текущая фаза: 0 — Скаффолд

- [x] Создать монорепо
- [x] Скаффолд `apps/web` (Vite + React + TS + Tailwind)
- [ ] Базовые роуты: Login, Inbox, Dashboard, Settings
- [x] Подключение к GitHub (origin)
- [x] Ветки `main` и `dev`
- [x] CI: GitHub Actions (typecheck + build) на push/PR в `main` и `dev`
- [x] Deploy workflow (заготовка, ждёт выбора хостинга)
- [ ] Настроить branch protection rules на GitHub (UI): `main` — требовать PR + зелёный CI

## Фаза 1 — MVP Frontend

- [x] Layout с боковым меню
- [x] Wizard «Подключение Bitrix24» (OAuth + webhook)
- [x] Callback-страница OAuth
- [x] Inbox: список диалогов (mock-данные)
- [x] Дашборд: объём, время ответа, sentiment (Recharts)
- [ ] Аутентификация (JWT)
- [ ] Темизация (dark/light)

## Фаза 2 — Backend MVP

- [x] Скаффолд `apps/api` (FastAPI + SQLAlchemy 2.0 async + SQLite)
- [x] Endpoints: health, integrations CRUD
- [x] Bitrix24 OAuth: создание подключения + exchange code → tokens
- [x] Bitrix24 webhook receiver (заглушка, логи)
- [x] CORS, Dockerfile
- [x] Pytest + ruff
- [x] Привязка фронтенда к backend (TanStack Query)
- [ ] Auth (JWT + multi-tenancy)
- [ ] Шифрование client_secret/токенов в БД
- [ ] Миграция SQLite → Postgres + Alembic-миграции
- [ ] Bitrix24: подписка на события через event.bind, обработка webhook'ов
- [ ] Ingestion pipeline (Celery + Redis)
- [ ] Базовый sentiment-анализ
- [ ] Endpoints inbox/dashboard на реальных данных

## Фаза 3 — Деплой

- [ ] docker-compose: api + web + postgres + redis
- [ ] Доработать `.github/workflows/deploy.yml` под выбранную инфраструктуру
