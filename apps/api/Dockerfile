# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Установка зависимостей отдельным слоем для кэша
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Код приложения и миграции
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY entrypoint.sh ./entrypoint.sh
# sed убирает CR на случай, если файл закоммитили с CRLF (Windows checkout).
RUN sed -i 's/\r$//' ./entrypoint.sh && chmod +x ./entrypoint.sh

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health',timeout=3).status==200 else 1)" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["serve"]
