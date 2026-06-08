"""QR-логин personal-аккаунтов Telegram.

Архитектура: in-process реестр `_REGISTRY[integration_id] -> _QRCtx`.
Каждый контекст держит живой Telethon-клиент и QRLogin-объект. Этого
достаточно для single-instance API; при горизонтальном масштабировании
(2+ uvicorn-воркера) нужно либо sticky-сессии на балансировщике, либо
вынос Telethon в отдельный connector-процесс (см. PLAN_CONNECTORS.md
§6.3). Для MVP — однопроцессный режим.

Состояния QR-flow:
- waiting           — QR-токен сгенерирован, ждём скан
- requires_password — скан прошёл, включён 2FA, нужен пароль
- connected         — авторизация завершена, StringSession сохранён в БД
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import get_settings
from app.integrations.telegram_user.client import (
    TelegramNotConfigured,
    make_client,
    serialize_session,
    session_password_needed_error,
)


class QRSessionNotFound(LookupError):
    """Контекст QR-логина для этой интеграции отсутствует или истёк."""


class QRSessionExpired(RuntimeError):
    """TTL контекста истёк, нужно перезапустить /qr/start."""


QRState = Literal["waiting", "requires_password", "connected"]


@dataclass
class _QRCtx:
    integration_id: str
    client: Any
    qr: Any  # telethon.tl.custom.QRLogin
    state: QRState = "waiting"
    created_at: float = field(default_factory=time.monotonic)
    # Защита от параллельных poll-вызовов на один контекст.
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Заполняется после connected:
    me: dict[str, Any] | None = None
    string_session: str | None = None


_REGISTRY: dict[str, _QRCtx] = {}


def _ttl() -> int:
    return get_settings().telegram_qr_ttl_sec


def _expired(ctx: _QRCtx) -> bool:
    return (time.monotonic() - ctx.created_at) > _ttl()


async def start_qr_session(integration_id: str) -> dict[str, Any]:
    """Создать новый Telethon-клиент и запросить QR-токен.

    Возвращает {"qr_url": "tg://login?token=...", "expires_in": <sec>}.
    """
    # Если был старый контекст — корректно убиваем.
    await teardown_qr_session(integration_id)

    client = make_client()  # бросит TelegramNotConfigured, если нет creds
    await client.connect()
    try:
        qr = await client.qr_login()
    except Exception:
        await client.disconnect()
        raise

    ctx = _QRCtx(integration_id=integration_id, client=client, qr=qr)
    _REGISTRY[integration_id] = ctx
    return {"qr_url": qr.url, "expires_in": _ttl()}


async def poll_qr_session(integration_id: str) -> dict[str, Any]:
    """Опросить статус QR-логина.

    Стратегия: ждём `qr.wait(timeout=1.5)` — короткий timeout, чтобы
    HTTP-запрос возвращался быстро. На таймаут — пересоздаём токен через
    qr.recreate() и отдаём новый url. На успех — сохраняем StringSession
    в ctx (вызывающий код вытаскивает его и пишет в БД).
    """
    ctx = _REGISTRY.get(integration_id)
    if ctx is None:
        raise QRSessionNotFound(integration_id)
    if _expired(ctx):
        await teardown_qr_session(integration_id)
        raise QRSessionExpired(integration_id)

    async with ctx.lock:
        if ctx.state == "connected":
            return _connected_payload(ctx)
        if ctx.state == "requires_password":
            return {"state": "requires_password"}

        PasswordNeeded = session_password_needed_error()
        try:
            user = await ctx.qr.wait(timeout=1.5)
        except PasswordNeeded:
            ctx.state = "requires_password"
            return {"state": "requires_password"}
        except TimeoutError:
            # токен мог истечь — пересоздаём, отдаём свежий url
            try:
                await ctx.qr.recreate()
            except Exception:  # noqa: S110, BLE001 — recreate best-effort
                pass
            return {
                "state": "waiting",
                "qr_url": ctx.qr.url,
                "expires_in": _ttl(),
            }
        else:
            # успешный вход без 2FA
            await _finalize_session(ctx, user)
            return _connected_payload(ctx)


async def confirm_password(
    integration_id: str, password: str
) -> dict[str, Any]:
    """Завершить вход после ввода 2FA-пароля."""
    ctx = _REGISTRY.get(integration_id)
    if ctx is None:
        raise QRSessionNotFound(integration_id)
    if _expired(ctx):
        await teardown_qr_session(integration_id)
        raise QRSessionExpired(integration_id)
    if ctx.state == "connected":
        return _connected_payload(ctx)

    async with ctx.lock:
        user = await ctx.client.sign_in(password=password)
        await _finalize_session(ctx, user)
        return _connected_payload(ctx)


async def teardown_qr_session(integration_id: str) -> None:
    """Гарантированно отключить Telethon-клиент и убрать контекст из реестра.

    Не падает, если контекста нет — корректно вызывается из start_qr_session
    как «сбросить предыдущий».
    """
    ctx = _REGISTRY.pop(integration_id, None)
    if ctx is None:
        return
    try:
        await ctx.client.disconnect()
    except Exception:  # noqa: S110, BLE001 — teardown best-effort
        pass


async def take_session_blob(integration_id: str) -> tuple[str, dict[str, Any]]:
    """Вытащить StringSession (для сохранения в БД) и инфу о пользователе.

    Должно вызываться после успешного poll/confirm_password. После вызова
    контекст можно безопасно удалить через teardown_qr_session.
    """
    ctx = _REGISTRY.get(integration_id)
    if ctx is None or ctx.state != "connected" or ctx.string_session is None:
        raise QRSessionNotFound(integration_id)
    return ctx.string_session, ctx.me or {}


async def _finalize_session(ctx: _QRCtx, user: Any) -> None:
    ctx.state = "connected"
    ctx.string_session = serialize_session(ctx.client)
    ctx.me = {
        "id": str(getattr(user, "id", "")),
        "first_name": getattr(user, "first_name", None),
        "last_name": getattr(user, "last_name", None),
        "username": getattr(user, "username", None),
        "phone": getattr(user, "phone", None),
    }


def _connected_payload(ctx: _QRCtx) -> dict[str, Any]:
    return {"state": "connected", "user": ctx.me}


__all__ = [
    "QRSessionExpired",
    "QRSessionNotFound",
    "TelegramNotConfigured",
    "confirm_password",
    "poll_qr_session",
    "start_qr_session",
    "take_session_blob",
    "teardown_qr_session",
]
