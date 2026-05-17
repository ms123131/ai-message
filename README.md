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

## Workflow разработки

- **`main`** — стабильная, всегда деплоимая в production. Прямые коммиты запрещены.
- **`dev`** — основная ветка разработки. Сюда мержатся feature-ветки.
- **`feature/<short-desc>`** — короткоживущие ветки от `dev`. Merge в `dev` через PR.
- **Релиз:** PR `dev → main` после прохождения CI и QA. Merge запускает `Deploy` workflow.
- **Hotfix:** ветка от `main`, PR в `main` + cherry-pick в `dev`.

```
feature/* ──▶ dev ──(PR + CI ✅)──▶ main ──▶ Deploy
```

### CI/CD

- **`.github/workflows/ci.yml`** — на каждый push/PR в `main` и `dev`: typecheck + build. Артефакт сборки сохраняется на 7 дней.
- **`.github/workflows/deploy.yml`** — на push в `main`: production-сборка. Сам шаг публикации появится после выбора хостинга (S3/Yandex Object Storage/k8s).

## Лицензия

Proprietary © 2026
