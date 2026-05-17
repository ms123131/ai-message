# Как продолжить работу в новой сессии

Если переписка с ассистентом потерялась после перезапуска ПК — этот файл вернёт контекст за минуту.

## Что есть сейчас

✅ Полностью рабочий **MVP-каркас** ai-message:

- Frontend (`apps/web`): React + Vite + Tailwind. Страницы Dashboard / Inbox / Integrations / Settings + Bitrix24-wizard с OAuth и webhook-режимами.
- Backend (`apps/api`): FastAPI + SQLAlchemy. Endpoints для интеграций и реальный обмен `code → access_token` с Bitrix24.
- Docker Compose: postgres + api + nginx-web, запуск одной командой.
- CI/CD: GitHub Actions — на каждый PR проверяет typecheck, build, тесты и собирает Docker-образ.

## Git состояние

- Репозиторий: https://github.com/ms123131/ai-message
- Ветки: `main` (production), `dev` (разработка)
- Локально: `/home/project/ai-message`

```bash
cd /home/project/ai-message
git status         # проверить состояние
git log --oneline -5
git fetch && git checkout dev && git pull
```

## Чтобы запустить проект

```bash
cd /home/project/ai-message
cp .env.example .env  # отредактировать POSTGRES_PASSWORD, JWT_SECRET
docker compose up -d --build
```

→ http://localhost:8080

## Что делать дальше

Открой [`docs/PLAN.md`](./PLAN.md) — там детальный roadmap по фазам.

**Следующая фаза (3) — реальные данные из Bitrix24:**
1. REST-клиент Bitrix24 с авто-refresh токена
2. Подписка на события через `event.bind`
3. Исторический импорт диалогов Open Channels
4. Модели `Conversation` и `Message` + API
5. Переключить Inbox/Dashboard с mock на реальные данные

## Полезные ссылки внутри репо

- `docs/PLAN.md` — полный план реализации с чек-листами
- `docs/DEPLOY.md` — инструкция по запуску через Docker и production-чек-лист
- `apps/api/README.md` — как запустить backend локально без Docker
- `README.md` (корень) — общая структура и workflow

## Команда для нового чата с ассистентом

Скопируй и вставь:

> Я работаю над проектом ai-message в `/home/project/ai-message`. Это chat-analysis SaaS с приоритетной интеграцией Bitrix24. Прочитай `docs/PLAN.md` и `docs/RESUME.md` — там полный контекст и roadmap. Текущая фаза работы — фаза 3 (реальные данные из Bitrix24). Продолжаем оттуда.
