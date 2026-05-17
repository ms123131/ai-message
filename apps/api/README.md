# ai-message-api

FastAPI-бэкенд для платформы анализа коммуникаций.

## Локальный запуск

```bash
cd apps/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# применить миграции
alembic upgrade head

# запустить
uvicorn app.main:app --reload --port 8000
```

API будет на http://localhost:8000, документация Swagger — http://localhost:8000/docs.

## Структура

```
app/
├── main.py              # FastAPI приложение
├── config.py            # Настройки (pydantic-settings)
├── db/                  # SQLAlchemy: engine, models, session
├── api/v1/              # REST endpoints
│   ├── health.py
│   ├── integrations.py
│   └── webhooks.py
├── integrations/        # Коннекторы CRM/мессенджеров
│   └── bitrix24/        # OAuth, REST-клиент, webhook-handler
└── schemas/             # Pydantic-схемы запросов/ответов
migrations/              # Alembic
tests/                   # Pytest
```

## Запуск через Docker

```bash
docker build -t ai-message-api .
docker run --rm -p 8000:8000 -v $(pwd)/data:/app/data ai-message-api
```
