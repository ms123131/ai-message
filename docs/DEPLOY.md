# Развёртывание через Docker

## Локальный запуск (single-host)

```bash
cp .env.example .env
# отредактируйте секреты (POSTGRES_PASSWORD, JWT_SECRET)

docker compose up -d --build
```

Доступ:
- Web: http://localhost:8080
- API напрямую: http://localhost:8000 (`/api/v1/health`, `/docs`)
- Postgres: localhost:5432

Остановить: `docker compose down`. Удалить данные тоже: `docker compose down -v`.

## Архитектура

```
              ┌──────────┐
   браузер ──►│  nginx   │ (web)  :8080
              │  /api/*  │───┐
              │  /webhooks│   │
              └──────────┘   ▼
                         ┌────────┐    ┌────────────┐
                         │  api   │───►│ postgres   │
                         │ :8000  │    │  :5432     │
                         └────────┘    └────────────┘
```

Фронтенд собирается с `VITE_API_URL=/api` и обращается к backend через тот же origin — CORS не нужен. Webhook'и от Bitrix24 принимаются на `/webhooks/bitrix24` (тоже проксируется в api).

## Production-чек-лист

- [ ] Закрыть `ports: 8000` и `ports: 5432` в `compose.yml`, оставить только `web:80` (или `:443`)
- [ ] Включить TLS: добавить traefik/caddy или сертификаты в nginx
- [ ] Заполнить `JWT_SECRET`, `POSTGRES_PASSWORD` сильными значениями
- [ ] Настроить бэкапы Postgres (`pg_dump` в S3/Object Storage по расписанию)
- [ ] Логи: `docker compose logs -f api` или агрегатор (Loki)
- [ ] Мониторинг: Prometheus + Grafana

## Обновление

```bash
git pull
docker compose up -d --build
```

Миграции БД на старте применяются автоматически (SQLAlchemy `create_all`).
Когда схема стабилизируется — переход на Alembic.
