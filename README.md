# ai-message — Chat Analysis Platform

SaaS-приложение для анализа всех коммуникационных каналов компании: email, мессенджеры, чаты CRM. Приоритетная интеграция — **Bitrix24**.

## Структура монорепо

```
ai-message/
├── apps/
│   ├── web/        # React + Vite + TypeScript (frontend)
│   └── api/        # FastAPI + Python (backend, фаза 2)
├── packages/       # общие пакеты (типы, UI, коннекторы) — будут добавлены
├── docs/           # документация и план реализации
└── infra/          # Docker, k8s, terraform — будут добавлены
```

## Технологический стек (кратко)

- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand, React Router
- **Backend (план):** Python 3.12, FastAPI, Celery, Redis, PostgreSQL 16 (+ pgvector)
- **Аналитика:** spaCy, transformers, BERTopic, sentence-transformers
- **Инфраструктура:** Docker, Kubernetes, GitHub Actions

Подробный план — см. [`docs/PLAN.md`](./docs/PLAN.md).

## Быстрый старт (frontend)

```bash
pnpm install
pnpm --filter @ai-message/web dev
```

Откроется на http://localhost:5173.

## Скрипты

| Команда | Описание |
|---|---|
| `pnpm dev` | Dev-сервер фронтенда |
| `pnpm build` | Production-сборка всех приложений |
| `pnpm lint` | Линтинг |
| `pnpm typecheck` | Проверка типов TypeScript |

## Лицензия

Proprietary © 2026
