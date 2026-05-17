# План реализации ai-message

Полный план — см. согласованный документ в чате. Этот файл служит «живой» проектной памятью и обновляется по мере развития.

## Текущая фаза: 0 — Скаффолд

- [x] Создать монорепо
- [x] Скаффолд `apps/web` (Vite + React + TS + Tailwind)
- [ ] Базовые роуты: Login, Inbox, Dashboard, Settings
- [ ] Подключение к GitHub (origin)
- [ ] CI: GitHub Actions (lint + typecheck + build)

## Следующая фаза: 1 — MVP Frontend

- [ ] Layout с боковым меню, темизация (dark/light)
- [ ] Страница «Подключение Bitrix24» (mock OAuth-wizard)
- [ ] Inbox: список диалогов (mock-данные)
- [ ] Просмотр диалога (таймлайн сообщений)
- [ ] Дашборд: объём, время ответа, sentiment (Recharts)
- [ ] Аутентификация (mock JWT)

## Фаза 2 — Backend MVP

- [ ] Скаффолд `apps/api` (FastAPI)
- [ ] Auth (JWT + multi-tenancy)
- [ ] Bitrix24 OAuth + webhook receiver
- [ ] Ingestion pipeline (Celery + Redis)
- [ ] Базовый sentiment-анализ
- [ ] REST API для inbox/dashboard
