"""Тесты Fernet-шифрования и EncryptedString TypeDecorator."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.security import crypto


@pytest.fixture
def fresh_cipher(monkeypatch):
    """Подменяет ENCRYPTION_KEY и сбрасывает кэши."""

    def _set(value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        else:
            monkeypatch.setenv("ENCRYPTION_KEY", value)
        get_settings.cache_clear()
        crypto.get_cipher.cache_clear()

    yield _set
    get_settings.cache_clear()
    crypto.get_cipher.cache_clear()


def test_roundtrip_with_explicit_key(fresh_cipher):
    key = Fernet.generate_key().decode()
    fresh_cipher(key)

    ct = crypto.encrypt_str("hello-secret")
    assert ct != "hello-secret"
    assert crypto.decrypt_str(ct) == "hello-secret"


def test_ephemeral_key_in_dev(fresh_cipher, monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    fresh_cipher(None)

    ct = crypto.encrypt_str("dev-secret")
    assert crypto.decrypt_str(ct) == "dev-secret"


def test_missing_key_in_production_raises(fresh_cipher, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    fresh_cipher(None)

    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        crypto.get_cipher()


def test_invalid_key_raises(fresh_cipher):
    fresh_cipher("not-a-valid-fernet-key")
    with pytest.raises(RuntimeError, match="невалиден"):
        crypto.get_cipher()


def test_rotation_with_multifernet(fresh_cipher):
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    # Сначала шифруем старым
    fresh_cipher(old_key)
    ct_old = crypto.encrypt_str("legacy-value")

    # Ротация: новый — активный, старый — для расшифровки
    fresh_cipher(f"{new_key},{old_key}")
    assert crypto.decrypt_str(ct_old) == "legacy-value"

    # Новые записи шифруются новым ключом
    ct_new = crypto.encrypt_str("fresh-value")
    assert crypto.decrypt_str(ct_new) == "fresh-value"

    # А старый ключ один такие уже не прочтёт
    fresh_cipher(old_key)
    with pytest.raises(InvalidToken):
        crypto.decrypt_str(ct_new)


def test_try_decrypt_returns_plain_for_legacy(fresh_cipher):
    fresh_cipher(Fernet.generate_key().decode())
    # plain-значение, оставшееся до миграции
    assert crypto.try_decrypt_str("legacy-plaintext") == "legacy-plaintext"


def test_try_decrypt_returns_plaintext_for_valid_token(fresh_cipher):
    fresh_cipher(Fernet.generate_key().decode())
    ct = crypto.encrypt_str("secret")
    assert crypto.try_decrypt_str(ct) == "secret"


@pytest.mark.asyncio
async def test_encrypted_string_typedecorator(fresh_cipher):
    """EncryptedString шифрует на write и расшифровывает на read."""
    from sqlalchemy import select, text

    from app.db.models import (
        Integration,
        IntegrationKind,
        IntegrationMode,
        IntegrationStatus,
    )
    from app.db.session import AsyncSessionLocal, Base, engine

    fresh_cipher(Fernet.generate_key().decode())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="enc_test_1",
            tenant_id=None,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="enc-test",
            domain="enc.bitrix24.ru",
            status=IntegrationStatus.connected,
            client_secret="my-client-secret",
            access_token="my-access-token",
            refresh_token="my-refresh-token",
        )
        session.add(integration)
        await session.commit()

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Integration).where(Integration.id == "enc_test_1")
        )
        row = res.scalar_one()
        assert row.client_secret == "my-client-secret"
        assert row.access_token == "my-access-token"
        assert row.refresh_token == "my-refresh-token"

    async with engine.connect() as conn:
        raw = (
            await conn.execute(
                text(
                    "SELECT client_secret, access_token, refresh_token "
                    "FROM integrations WHERE id = :id"
                ),
                {"id": "enc_test_1"},
            )
        ).one()
        assert raw[0] != "my-client-secret"
        assert raw[1] != "my-access-token"
        assert raw[2] != "my-refresh-token"
        assert crypto.decrypt_str(raw[0]) == "my-client-secret"
        assert crypto.decrypt_str(raw[1]) == "my-access-token"
        assert crypto.decrypt_str(raw[2]) == "my-refresh-token"


def test_encrypted_string_none_passthrough():
    """None в БД остаётся None — не шифруется и не падает на чтении."""
    from app.security.types import EncryptedString

    t = EncryptedString()
    assert t.process_bind_param(None, None) is None
    assert t.process_result_value(None, None) is None
