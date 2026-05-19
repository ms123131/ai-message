#!/usr/bin/env sh
# Entrypoint Docker-образа api.
# - run-migrations: применить миграции и выйти (для one-shot сервиса в compose)
# - run-worker: запустить arq-воркер фоновых задач (отдельный контейнер)
# - serve (default): только запустить uvicorn (миграции — отдельным сервисом)
set -eu

cmd="${1:-serve}"

case "$cmd" in
  run-migrations)
    echo "[entrypoint] alembic upgrade head"
    exec alembic upgrade head
    ;;
  run-worker)
    echo "[entrypoint] starting arq worker"
    exec arq app.workers.settings.WorkerSettings
    ;;
  serve)
    echo "[entrypoint] starting uvicorn"
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    ;;
  *)
    # Любая другая команда — пробрасываем как есть (debug shell и т.п.)
    exec "$@"
    ;;
esac
