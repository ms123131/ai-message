# План интеграции коннекторов: Telegram Bot → Personal Telegram → WhatsApp

Дочерний документ к `docs/PLAN.md`. Содержит детали по фазе 8 (новые каналы)
и универсальному механизму верификации подключений.

## Очерёдность

1. Telegram Bot — простой REST, минимальный риск.
2. Verifier-фреймворк (закладывается на TG Bot, переиспользуется дальше).
3. **Personal Telegram (QR-логин)** — в реализации.
4. WhatsApp Personal (Wazzup или Baileys — решение перед стартом).

---

## Personal Telegram — QR-логин

### Почему QR

- Официально поддерживается MTProto (`auth.exportLoginToken` /
  `auth.acceptLoginToken` / `auth.importLoginToken`). Тот же механизм
  использует Telegram Desktop в режиме «Войти по QR».
- В Telethon — высокоуровневый `await client.qr_login()`, возвращающий
  объект `QRLogin` с `.url` (формат `tg://login?token=...base64url`),
  `.wait(timeout)` и `.recreate()`.
- Не нужны SMS/звонок, не нужно собирать `phone_code_hash`.
- 2FA-пароль обрабатывается тем же путём, что в phone-flow:
  `qr.wait()` → `SessionPasswordNeededError` → второй шаг ввода пароля.

### Допущения

- У компании зарегистрировано одно Telegram-приложение на
  `my.telegram.org` → `api_id` + `api_hash` лежат в `.env` (общие на всех
  пользователей).
- Пользователь явно даёт согласие на чтение personal-чатов
  (UI-дисклеймер).
- Подключение валидно, только если у пользователя есть второе устройство
  с залогиненным Telegram, способное отсканировать QR. Иначе — fallback
  на phone+code (вторая фаза, не входит в первый релиз).

### Поток (UX)

1. `Integrations → Add → Telegram (личный аккаунт)`.
2. Backend `POST /api/v1/integrations/telegram-user/qr/start`:
   - Создаёт `Integration(kind=telegram_user, mode=qr_link,
     status=pending, tenant_id=<user.tenant>)`.
   - Поднимает Telethon-клиент с `StringSession()` (пустая) и общими
     `api_id/api_hash`. Вызывает `qr = await client.qr_login()`.
   - Сериализует `QRLogin` (а точнее — держит Telethon-клиент живым в
     in-process registry `qr_sessions: dict[integration_id, _QRCtx]`,
     потому что переподключиться без той же сессии нельзя). TTL 5 мин.
   - Отвечает `{integration_id, qr_url, expires_at}`.
3. Frontend рендерит QR из `qr_url` через `qrcode.react`. Параллельно
   опрашивает `POST /api/v1/integrations/telegram-user/{id}/qr/poll`
   каждые 2 сек.
4. Сервер на каждый `poll`:
   - Если контекст по `integration_id` не найден / истёк — `410 Gone`,
     UI начинает заново.
   - Ждёт `await qr.wait(timeout=1.5)` (короткий timeout — чтобы запрос
     возвращался быстро):
     - `User` → успех. Сохраняем `StringSession`, `me.id`,
       `me.first_name`, `me.phone`. `status=connected`. Возврат
       `{state: "connected", user: {...}}`.
     - `SessionPasswordNeededError` → `{state: "requires_password"}`,
       UI открывает ввод пароля.
     - `asyncio.TimeoutError` → `qr.recreate()` если истёк, иначе тот же
       QR. Возврат `{state: "waiting", qr_url, expires_at}`.
5. При 2FA: `POST .../password {password}` → `await client.sign_in(
   password=...)`. Дальше тот же save.

### Хранение сессии

- `Integration.auth_blob: EncryptedString` — Fernet-зашифрованная
  `StringSession.save()` (~370 байт base64).
- `Integration.domain` = телефон в E.164 (для UI/уникальности).
- `Integration.label` = `f"{first_name} {last_name}".strip() or domain`.
- `Integration.member_id` = строка из `me.id` (числовой ID юзера TG).

### Реализация — расклад файлов

```
apps/api/app/integrations/telegram_user/
├── __init__.py
├── client.py        # фабрика TelegramClient из StringSession
├── qr_auth.py       # QR registry + старт/poll/password
└── verifier.py      # проверка connect/get_me (для §5 verify)

apps/api/app/api/v1/
└── integrations_telegram_user.py   # роутер /telegram-user

apps/api/migrations/versions/
└── 0013_telegram_integration.py    # enum + новые поля
```

### Конфиг (`Settings`)

- `TELEGRAM_API_ID: int | None`
- `TELEGRAM_API_HASH: str | None`
- `TELEGRAM_SESSION_ENCRYPTION_KEY: str | None` — отдельный Fernet-ключ
  для `auth_blob` (defense-in-depth; если не задан — используем общий
  `ENCRYPTION_KEY`).
- `TELEGRAM_QR_TTL_SEC: int = 300`

### Безопасность

- В production отсутствие `TELEGRAM_API_ID/HASH` → 503 при запросе
  `qr/start`, а не падение процесса.
- StringSession **никогда** не отдаётся через API, не пишется в логи.
- Аудит: `integration.telegram_user.connect`, `...disconnect`,
  `...auth_failed`.
- При удалении интеграции — `await client.log_out()` + затирание
  `auth_blob`. Если log_out упал (сессия уже мертва) — всё равно
  удаляем запись.

### Что НЕ делаем в первой итерации

- Long-running connector-процесс (приём `@events.NewMessage`) —
  отдельной задачей; QR-MVP только устанавливает сессию и проверяет
  `verify`. После подключения сообщения пока не льются в Inbox.
- Phone+code fallback — после QR-MVP, если потребуется.
- Исторический импорт диалогов — после connector-процесса.

---

## Verifier (черновик, реализуется отдельно)

Универсальный `POST /integrations/{id}/verify` со списком проверок
`auth` / `transport` / `webhook` / `echo`. См. §5 в исходном плане
обсуждения. Для `telegram_user` базовая проверка — `get_me()`.
