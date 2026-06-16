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


def _build_proxy() -> dict[str, Any] | None:
    """Собрать proxy-конфиг для Telethon из настроек, либо None (прямое соединение).

    Формат — dict для python-socks (Telethon его и использует асинхронно).
    Нужен, когда egress окружения к сетям Telegram заблокирован: трафик MTProto
    тогда идёт через SOCKS5 (в k8s — Xray-Deployment, см. infra/k8s/12-xray.yaml).
    """
    settings = get_settings()
    kind = (settings.telegram_proxy_kind or "none").lower()
    if kind in ("", "none"):
        return None
    if kind != "socks5":
        raise TelegramNotConfigured(f"unsupported telegram_proxy_kind: {kind!r}")
    if not settings.telegram_proxy_host:
        raise TelegramNotConfigured(
            "telegram_proxy_kind=socks5, но TELEGRAM_PROXY_HOST не задан"
        )
    proxy: dict[str, Any] = {
        "proxy_type": "socks5",
        "addr": settings.telegram_proxy_host,
        "port": settings.telegram_proxy_port,
        # rdns=True: DNS-резолв имён делает сам прокси (на нашей стороне
        # Telegram-домены могут не резолвиться/быть отравлены).
        "rdns": True,
    }
    if settings.telegram_proxy_user:
        proxy["username"] = settings.telegram_proxy_user
        proxy["password"] = settings.telegram_proxy_pass or ""
    return proxy


def make_client(string_session: str = ""):
    """Создать неподключённый TelegramClient (StringSession + dev/prod creds).

    Подключение делает вызывающий код через `await client.connect()`.
    Если задан telegram_proxy_* — MTProto пойдёт через SOCKS5.
    """
    TelegramClient, StringSession, _ = _require_telethon()
    api_id, api_hash = require_api_credentials()
    return TelegramClient(
        StringSession(string_session), api_id, api_hash, proxy=_build_proxy()
    )


def session_password_needed_error() -> type[Exception]:
    _, _, exc = _require_telethon()
    return exc


def serialize_session(client) -> str:
    """Достать StringSession.save() из живого клиента."""
    return client.session.save()
