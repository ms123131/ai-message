"""
Bitrix24 OAuth 2.0 — обмен авторизационного кода на токены.

Документация:
  https://apidocs.bitrix24.ru/api-reference/oauth/index.html
"""

from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from app.config import get_settings


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    client_endpoint: str | None = None
    server_endpoint: str | None = None
    domain: str | None = None
    member_id: str | None = None
    scope: str | None = None
    expires_in: int = 3600
    status: str | None = None


class BitrixOAuthError(RuntimeError):
    def __init__(self, error: str, description: str | None = None) -> None:
        super().__init__(f"{error}: {description}" if description else error)
        self.error = error
        self.description = description


def build_authorize_url(domain: str, client_id: str, state: str) -> str:
    """Формирует URL для перенаправления пользователя на портал."""
    params = urlencode({"client_id": client_id, "state": state})
    return f"https://{domain}/oauth/authorize/?{params}"


async def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
) -> TokenResponse:
    """
    Обменивает первый авторизационный `code` на пару (access_token, refresh_token).

    Запрос идёт на единый сервер авторизации oauth.bitrix24.tech, а не на портал.
    Время жизни `code` — 30 секунд, поэтому вызов должен происходить сразу
    после получения от портала.
    """
    settings = get_settings()
    params = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(settings.bitrix24_oauth_token_url, params=params)
        data = resp.json()
    if "error" in data:
        raise BitrixOAuthError(data["error"], data.get("error_description"))
    return TokenResponse.model_validate(data)


async def refresh_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token_value: str,
) -> TokenResponse:
    """Обновляет пару токенов по refresh_token."""
    settings = get_settings()
    params = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token_value,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(settings.bitrix24_oauth_token_url, params=params)
        data = resp.json()
    if "error" in data:
        raise BitrixOAuthError(data["error"], data.get("error_description"))
    return TokenResponse.model_validate(data)
