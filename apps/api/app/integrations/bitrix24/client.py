"""
Bitrix24 REST-клиент.

Возможности:
* OAuth: использует `Integration.access_token`, авто-refresh за `REFRESH_LEEWAY`
  до истечения и при ответе `expired_token` (один retry). Credentials берутся
  из settings (`BITRIX24_APP_CLIENT_ID/SECRET`) — одно тиражное приложение
  на всех клиентов.
* Throttling: не более `MAX_RPS` запросов в секунду на портал (глобальный реестр).
* `batch()` — до 50 команд за один HTTP-запрос (метод `batch` REST API).

Документация:
  https://apidocs.bitrix24.ru/api-reference/rest-sdk/index.html
  https://apidocs.bitrix24.ru/api-reference/how-to-call-rest-api/batch.html
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Integration, IntegrationMode, IntegrationStatus
from app.integrations.bitrix24.oauth import (
    BitrixOAuthError,
    TokenResponse,
    refresh_token,
)

MAX_RPS = 2
REFRESH_LEEWAY = timedelta(minutes=5)
DEFAULT_TIMEOUT = 30.0
BATCH_LIMIT = 50


class BitrixAPIError(RuntimeError):
    """Bitrix24 вернул ошибку (поле `error` в JSON)."""

    def __init__(self, error: str, description: str | None = None) -> None:
        super().__init__(f"{error}: {description}" if description else error)
        self.error = error
        self.description = description


class BitrixIntegrationStateError(RuntimeError):
    """Интеграция не готова к использованию (нет токенов / домена)."""


class _PortalThrottle:
    """
    Гарантирует минимальный интервал `1/MAX_RPS` между REST-вызовами одного портала.

    Семафоры/таймстемпы хранятся per-portal-key в class-level словаре,
    так что разные экземпляры BitrixClient к одному порталу делят лимит.
    """

    _locks: dict[str, asyncio.Lock] = {}
    _next_allowed: dict[str, float] = {}

    @classmethod
    def _lock_for(cls, key: str) -> asyncio.Lock:
        lock = cls._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[key] = lock
        return lock

    @classmethod
    async def acquire(cls, key: str) -> None:
        lock = cls._lock_for(key)
        async with lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            next_at = cls._next_allowed.get(key, 0.0)
            if now < next_at:
                await asyncio.sleep(next_at - now)
                now = loop.time()
            cls._next_allowed[key] = now + 1.0 / MAX_RPS


PersistCallback = Callable[[Integration], Awaitable[None]]


def _now() -> datetime:
    return datetime.now(UTC)


class BitrixClient:
    """
    Лёгкий клиент над одной `Integration`.

    `session` нужен для персистенции обновлённых токенов после авто-refresh.
    Транспорт можно подменить через `transport` для тестов.
    """

    def __init__(
        self,
        integration: Integration,
        session: AsyncSession,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        now: Callable[[], datetime] = _now,
    ) -> None:
        self.integration = integration
        self.session = session
        self._timeout = timeout
        self._now = now
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout)

    async def __aenter__(self) -> BitrixClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def _throttle_key(self) -> str:
        i = self.integration
        return i.member_id or i.domain or i.id

    def _build_url(self, method: str) -> str:
        i = self.integration
        if not i.domain:
            raise BitrixIntegrationStateError("domain is empty")
        return f"https://{i.domain}/rest/{method}.json"

    async def _ensure_fresh_token(self) -> None:
        i = self.integration
        if i.mode != IntegrationMode.oauth:
            return
        if not (i.access_token and i.refresh_token):
            raise BitrixIntegrationStateError("OAuth tokens are missing")
        if i.expires_at and i.expires_at - self._now() > REFRESH_LEEWAY:
            return
        await self._refresh()

    async def _refresh(self) -> None:
        from app.config import get_settings

        i = self.integration
        settings = get_settings()
        # Credentials глобальные (одно тиражное приложение). Per-integration
        # client_id/secret поддерживаем как fallback для старых OAuth-записей.
        client_id = settings.bitrix24_app_client_id or i.client_id
        client_secret = settings.bitrix24_app_client_secret or i.client_secret
        if not (client_id and client_secret and i.refresh_token):
            raise BitrixIntegrationStateError(
                "OAuth credentials are missing (BITRIX24_APP_CLIENT_ID/SECRET в .env?)"
            )
        try:
            tokens: TokenResponse = await refresh_token(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token_value=i.refresh_token,
            )
        except BitrixOAuthError:
            i.status = IntegrationStatus.error
            await self.session.flush()
            raise
        i.access_token = tokens.access_token
        i.refresh_token = tokens.refresh_token
        i.expires_at = self._now() + timedelta(seconds=tokens.expires_in)
        if tokens.scope:
            i.scope = tokens.scope
        if tokens.member_id:
            i.member_id = tokens.member_id
        i.status = IntegrationStatus.connected
        await self.session.flush()

    def _auth_params(self) -> dict[str, str]:
        return {"auth": self.integration.access_token or ""}

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        url = self._build_url(method)
        await _PortalThrottle.acquire(self._throttle_key)
        body = urlencode(params, doseq=True)
        resp = await self._client.post(
            url,
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = resp.json()
        return data

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """
        Вызов одного REST-метода. Возвращает значение поля `result` из ответа.

        При истёкшем access_token делает один авто-refresh и retry.
        """
        await self._ensure_fresh_token()
        payload = {**(params or {}), **self._auth_params()}
        data = await self._request(method, payload)

        if data.get("error") == "expired_token" and self.integration.mode == IntegrationMode.oauth:
            await self._refresh()
            payload = {**(params or {}), **self._auth_params()}
            data = await self._request(method, payload)

        if "error" in data:
            raise BitrixAPIError(data["error"], data.get("error_description"))
        return data.get("result")

    async def batch(
        self,
        commands: dict[str, str],
        *,
        halt: bool = False,
    ) -> dict[str, Any]:
        """
        Пакетный вызов через метод `batch`.

        `commands` — словарь `{ключ: "method?param1=...&param2=..."}` (как требует API).
        Возвращает словарь `{ключ: result}` из ответа.
        """
        if len(commands) > BATCH_LIMIT:
            raise ValueError(f"batch supports up to {BATCH_LIMIT} commands, got {len(commands)}")
        params: dict[str, Any] = {"halt": 1 if halt else 0}
        for key, cmd in commands.items():
            params[f"cmd[{key}]"] = cmd
        result = await self.call("batch", params)
        if not isinstance(result, dict):
            return {}
        cmd_results = result.get("result", {}) or {}
        if isinstance(cmd_results, dict):
            return cmd_results
        return {}
