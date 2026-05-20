"""encrypt integration secrets (client_secret, access_token, refresh_token)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-20

Шифрует plain-значения в столбцах `integrations.client_secret`,
`access_token`, `refresh_token` через Fernet (см. `app.security.crypto`).
Идемпотентно: если значение уже зашифровано (валидный Fernet-токен),
оставляет как есть. Для downgrade — расшифровываем обратно.

ВАЖНО: миграция требует доступного `ENCRYPTION_KEY` в окружении. Без
ключа в production миграция упадёт ещё на импорте модуля, что нам и
нужно — нельзя выкатить шифрование без ключа.

DDL изменений нет: исходные столбцы — `String(255)` и `Text`,
ciphertext тоже строка. Тип в моделях стал `EncryptedString` (TypeDecorator
поверх Text), но физический тип столбца совместим.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.security.crypto import decrypt_str, encrypt_str, try_decrypt_str

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLUMNS = ("client_secret", "access_token", "refresh_token")


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, client_secret, access_token, refresh_token FROM integrations"
        )
    ).mappings().all()

    for row in rows:
        updates: dict[str, str] = {}
        for col in _COLUMNS:
            val = row[col]
            if val is None or val == "":
                continue
            # try_decrypt_str вернёт plaintext если это уже Fernet-токен —
            # значит шифровать повторно не нужно. Если value совпадает с
            # try_decrypt_str(value), то это был plain.
            decrypted = try_decrypt_str(val)
            if decrypted == val:
                # plain → шифруем
                updates[col] = encrypt_str(val)
            # иначе — уже ciphertext, пропускаем
        if updates:
            set_clause = ", ".join(f"{c} = :{c}" for c in updates)
            bind.execute(
                sa.text(f"UPDATE integrations SET {set_clause} WHERE id = :id"),
                {**updates, "id": row["id"]},
            )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, client_secret, access_token, refresh_token FROM integrations"
        )
    ).mappings().all()

    for row in rows:
        updates: dict[str, str] = {}
        for col in _COLUMNS:
            val = row[col]
            if val is None or val == "":
                continue
            try:
                updates[col] = decrypt_str(val)
            except Exception:  # noqa: BLE001
                # Уже plain — оставляем
                continue
        if updates:
            set_clause = ", ".join(f"{c} = :{c}" for c in updates)
            bind.execute(
                sa.text(f"UPDATE integrations SET {set_clause} WHERE id = :id"),
                {**updates, "id": row["id"]},
            )
