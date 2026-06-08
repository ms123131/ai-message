"""Фабрика Telethon-клиентов.

Импортируется лениво: если пакет `telethon` не установлен, поднимаем
`TelegramNotConfigured` в момент первого использования, чтобы остальной
API продолжал работать (как natasha/sentence-transformers).
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings


class TelegramNotConfigured(RuntimeError):
    """API_ID/API_HASH не заданы или telethon недоступен."""


def _require_telethon() -> tuple[Any, Any, Any]:
    try:
        from telethon import TelegramClient  # type: ignore[import-not-found]
        from telethon.errors import (  # type: ignore[import-not-found]
            SessionPasswordNeededError,
        )
        from telethon.sessions import (  # type: ignore[import-not-found]
            StringSession,
        )
    except ImportError as exc:  # pragma: no cover — graceful degrade
        raise TelegramNotConfigured(
            "telethon package is not installed"
        ) from exc
    return TelegramClient, StringSession, SessionPasswordNeededError


def require_api_credentials() -> tuple[int, str]:
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise TelegramNotConfigured(
            "TELEGRAM_API_ID/TELEGRAM_API_HASH are not set"
        )
    return settings.telegram_api_id, settings.telegram_api_hash


def make_client(string_session: str = ""):
    """Создать неподключённый TelegramClient (StringSession + dev/prod creds).

    Подключение делает вызывающий код через `await client.connect()`.
    """
    TelegramClient, StringSession, _ = _require_telethon()
    api_id, api_hash = require_api_credentials()
    return TelegramClient(StringSession(string_session), api_id, api_hash)


def session_password_needed_error() -> type[Exception]:
    _, _, exc = _require_telethon()
    return exc


def serialize_session(client) -> str:
    """Достать StringSession.save() из живого клиента."""
    return client.session.save()
