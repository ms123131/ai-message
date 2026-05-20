"""Rate limiting через slowapi.

Стратегия ключа:
- если запрос аутентифицирован — лимит per-tenant (через JWT `tid`);
- иначе — per-IP (через `X-Forwarded-For`, выставляется nginx).

Лимиты применяются точечно к чувствительным эндпоинтам: auth (брутфорс
паролей), enqueue импорта (DoS на Bitrix через перезапуск).

В тестах лимиты не отключаем — наоборот, отдельный тест проверяет, что
после порога приходит 429. Для остальных тестов лимиты заведомо выше
их активности.
"""

from __future__ import annotations

import logging

import jwt
from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

from app.config import get_settings

logger = logging.getLogger(__name__)


def _tenant_or_ip_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            settings = get_settings()
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=["HS256"],
                options={"verify_exp": False},
            )
            tid = payload.get("tid")
            if tid:
                return f"tenant:{tid}"
        except jwt.PyJWTError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_tenant_or_ip_key, headers_enabled=False)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:  # noqa: ARG001
    logger.warning("rate limit exceeded: %s", exc.detail)
    return JSONResponse(
        status_code=429,
        content={"detail": f"Too many requests: {exc.detail}"},
    )
