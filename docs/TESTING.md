# End-to-end тест: приём сообщения из Bitrix24 Open Channels

Цель — убедиться, что цикл «сообщение в чате на портале → запись в БД ai-message → виден через REST» работает. Без AI/анализа, чистая транспортная часть.

## 0. Что должно быть установлено

- Docker Desktop (Windows) или Docker Engine (Linux).
- Аккаунт на портале Bitrix24 (можно бесплатный) с правами администратора.
- ngrok или Cloudflare Tunnel — чтобы Bitrix24 мог достучаться до вашего локального стека (порт 8080 наружу).

## 1. Запуск стека

```bash
cd ai-message
cp .env.example .env
# Поправьте в .env:
#   POSTGRES_PASSWORD=<свой>
#   JWT_SECRET=<длинная случайная строка>
#   VITE_API_URL=         (оставить пустым)
#   WEBHOOK_BASE_URL=     (пока пусто, заполним после ngrok)

docker compose up -d --build
```

Проверьте:

```bash
curl http://localhost:8080/api/v1/health
# {"status":"ok","version":"0.0.1"}
```

UI: <http://localhost:8080>.

> **Внимание:** между крупными обновлениями схемы БД сейчас нужен `docker compose down -v` (volume сносится) — Alembic-миграций пока нет, таблицы создаются через `Base.metadata.create_all`, новые колонки на существующую БД не накатятся. Это в техдолге.

## 2. Публичный URL через ngrok

В отдельном терминале:

```bash
ngrok http 8080
```

Скопируйте `https://<random>.ngrok-free.app` и пропишите в `.env`:

```
WEBHOOK_BASE_URL=https://<random>.ngrok-free.app
```

Перезапустите api, чтобы он перечитал переменную:

```bash
docker compose up -d api
```

## 3. Подключение портала

### Вариант A — входящий webhook (быстрее для теста)

1. В Bitrix24: **Разработчикам → Другое → Входящий вебхук**.
2. Выдайте права как минимум: `imopenlines`, `event`, `event_bind`.
3. Скопируйте URL вида `https://yourportal.bitrix24.ru/rest/1/abcdef12345/`.
4. В UI ai-message: **Интеграции → Подключить Bitrix24 → Входящий webhook** — вставьте URL.

### Вариант B — OAuth-приложение (как у боевых клиентов)

1. **Разработчикам → Другое → Локальное приложение**.
2. Тип: «Серверное».
3. Перенаправление: `https://<your-ngrok>/integrations/bitrix24/callback`.
4. Права: `imopenlines`, `event`, `event_bind`.
5. Сохраните `client_id` (`local.xxxxx`) и `client_secret`.
6. В UI: **Подключить Bitrix24 → OAuth** — введите домен портала, client_id, client_secret. Кликните «Авторизовать», подтвердите на портале.

## 4. Подписка на события

После того как интеграция в статусе `connected`, узнайте её `id`:

```bash
curl http://localhost:8080/api/v1/integrations
# [{"id":"b24_xxxxxxxx", "status":"connected", ...}]
```

Зарегистрируйте обработчик:

```bash
curl -X POST http://localhost:8080/api/v1/integrations/b24_xxxxxxxx/events/subscribe
```

Ожидаемый ответ:

```json
{
  "handler": "https://<ngrok>/webhooks/bitrix24",
  "events": ["OnImOpenLinesMessageAdd", "OnImOpenLinesSessionStart", "OnImOpenLinesSessionFinish"],
  "results": [
    {"event": "OnImOpenLinesMessageAdd", "result": {...}},
    ...
  ]
}
```

Если у события `error=ERROR_HANDLER_ALREADY_BINDED` — оно уже было привязано, это ок.

## 5. Открытая линия и тестовое сообщение

1. Bitrix24: **CRM → Контакт-центр → Открытые линии → создать линию**, подключите тестовый коннектор (проще всего «Онлайн-чат» — виджет для сайта).
2. Откройте предоставленную ссылку виджета (или установите его на тестовую страницу).
3. Напишите сообщение от имени клиента.

## 6. Проверка

```bash
# Все диалоги:
curl http://localhost:8080/api/v1/conversations | jq

# Сообщения конкретного диалога:
curl http://localhost:8080/api/v1/conversations/<conv_id>/messages | jq

# В логах api:
docker compose logs -f api | grep bitrix24
```

Должен прилететь `event=ONIMOPENLINESMESSAGEADD ... ingested`, а в `/conversations` — запись с правильным каналом, контактом и текстом.

## 7. Если не работает

- `result=no_integration` — пришло событие, но мы не нашли интеграцию по `member_id`/`domain`. Убедитесь, что портал успешно прошёл OAuth и в `/integrations` у записи есть `member_id`.
- `result=unsupported` — мы получили событие, которое не парсим (например, `OnImOpenLinesSessionStart` — он есть в подписках, но не превращается в Message). Это нормально.
- Bitrix24 не дёргает webhook вовсе — проверьте `WEBHOOK_BASE_URL`, доступность через ngrok, что в права приложения добавлен `event_bind`, и что `event.bind` отработал.
- 502 от nginx — `api` контейнер ещё стартует или упал, посмотрите `docker compose logs api`.
