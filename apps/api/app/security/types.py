"""SQLAlchemy TypeDecorator для прозрачного шифрования строк.

Используется в колонках с секретами (см. `Integration.client_secret`,
`access_token`, `refresh_token`). Работа с ORM не меняется: присваиваем
plain — в БД уходит ciphertext, читаем — получаем plain.

На чтение используем `try_decrypt_str`, чтобы при первом запуске после
выкатки шифрования (до прогона data-миграции) старые plain-значения не
ломали приложение.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.security.crypto import encrypt_str, try_decrypt_str


class EncryptedString(TypeDecorator):
    """Fernet-зашифрованная строка. Хранится как TEXT (ciphertext длиннее plaintext)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        return encrypt_str(value)

    def process_result_value(self, value: Any, dialect: Any) -> str | None:  # noqa: ARG002
        if value is None:
            return None
        return try_decrypt_str(value)
