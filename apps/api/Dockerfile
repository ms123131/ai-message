# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_HTTP_TIMEOUT=300 \
    UV_CONCURRENT_DOWNLOADS=4

WORKDIR /app

# uv вместо pip: HTTP/2, агрессивные параллельные ретраи с back-off,
# нативный resolver. В контексте этого проекта особенно важно: pypi.org
# периодически рвёт TLS-соединения посреди стрима (SSL EOF), и pip-у
# на этом плохо — uv переподключается без потери прогресса.
#
# Если pypi всё равно недоступен/блокируется — раскомментируйте
# UV_INDEX_URL ниже, чтобы тянуть зеркало.
#
# Cache mount на uv-store переживает между сборками, в финальный образ
# не попадает. Холодная сборка тянет torch/sentence-transformers (~1.5 ГБ),
# повторные за секунды.
COPY pyproject.toml ./
# ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
RUN --mount=type=cache,id=uv-cache,target=/root/.cache/uv \
    pip install --no-cache-dir uv \
    && uv pip install --system .

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
