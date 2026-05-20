"""Симметричное шифрование чувствительных полей в БД (Fernet).

Зачем: `Integration.client_secret`, `access_token`, `refresh_token` — это
ключи доступа к порталу клиента. В plain text дамп БД == полный угон портала.
Fernet (AES-128-CBC + HMAC-SHA256) даёт прозрачное шифрование на уровне
ORM-колонки.

Ключ берётся из `ENCRYPTION_KEY` (формат — base64 url-safe 32 байта, как
выдаёт `Fernet.generate_key()`). Для ротации поддерживается несколько
ключей через запятую: первый — активный (им шифруем при записи),
остальные — для расшифровки старых данных через `MultiFernet`.

В `app_env=production` отсутствие ключа — фатальная ошибка. В dev/test
генерируем эпhemerал-ключ в памяти (с предупреждением), чтобы локальный
запуск и тесты не требовали ручной настройки.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings

logger = logging.getLogger(__name__)


def _parse_keys(raw: str) -> list[bytes]:
    keys: list[bytes] = []
    for part in raw.split(","):
        k = part.strip()
        if not k:
            continue
        keys.append(k.encode("utf-8"))
    return keys


@lru_cache
def get_cipher() -> MultiFernet:
    """MultiFernet с активным ключом + дополнительными для ротации.

    Кэшируется на процесс. Для тестов с подменой env-переменных используйте
    `get_cipher.cache_clear()`.
    """
    settings = get_settings()
    raw = (settings.encryption_key or "").strip()

    if not raw:
        if settings.app_env == "production":
            raise RuntimeError(
                "ENCRYPTION_KEY is required when APP_ENV=production. "
                "Сгенерируйте ключ: python -c "
                "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        # dev/test: эпhemerал-ключ. Перезапуск процесса = потеря данных,
        # это ОК для локальной отладки и юнит-тестов.
        ephemeral = Fernet.generate_key()
        logger.warning(
            "ENCRYPTION_KEY не задан — сгенерирован эпhemerал-ключ (app_env=%s). "
            "Зашифрованные данные не переживут перезапуск процесса.",
            settings.app_env,
        )
        return MultiFernet([Fernet(ephemeral)])

    keys = _parse_keys(raw)
    if not keys:
        raise RuntimeError("ENCRYPTION_KEY пуст после парсинга")
    try:
        fernets = [Fernet(k) for k in keys]
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"ENCRYPTION_KEY невалиден ({exc}). Ожидается Fernet-ключ "
            "(base64 url-safe 32 байта)."
        ) from exc
    return MultiFernet(fernets)


def encrypt_str(value: str) -> str:
    """Шифрует строку, возвращает ciphertext (str, urlsafe-base64)."""
    return get_cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    """Расшифровывает ciphertext в строку.

    Бросает `cryptography.fernet.InvalidToken`, если значение не зашифровано
    или подписано неизвестным ключом.
    """
    return get_cipher().decrypt(token.encode("ascii")).decode("utf-8")


def try_decrypt_str(value: str) -> str:
    """Терпимый к plain-тексту вариант для миграционного периода.

    Если значение похоже на Fernet-токен и расшифровывается — возвращает
    plaintext. Иначе считает, что это уже plain (легаси) и возвращает как есть.
    Использовать только в data-миграции и в TypeDecorator на чтение.
    """
    try:
        return decrypt_str(value)
    except InvalidToken:
        return value
    except Exception:  # noqa: BLE001
        # Битый base64 и т.п. — тоже считаем за легаси-plain
        return value
