# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Системные зависимости (минимум — для будущего postgres/asyncpg, healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей отдельным слоем для кэша
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Код приложения
COPY app ./app

# Миграции (alembic.ini + migrations/) добавим, когда схема стабилизируется.
# Пока таблицы создаются автоматически в lifespan через SQLAlchemy.

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
