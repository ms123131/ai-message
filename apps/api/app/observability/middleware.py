"""HTTP-middleware: request_id + структурированный access-лог.

Поведение:
- если входящий запрос содержит `X-Request-Id` — используем как есть
  (трасса клиента / шлюза проксируется через нас);
- иначе генерируем короткий UUID4.
- значение кладётся в `request_id_var` (ContextVar) и заголовок ответа,
  чтобы клиент мог сослаться на конкретный запрос в support-тикете.
- access-лог пишется одним JSON-сообщением `http_request` с method/path/
  status/duration_ms — без дубля от uvicorn.access (его отключаем).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.logging import get_logger, request_id_var

logger = get_logger(__name__)

_REQ_ID_HEADER = "X-Request-Id"


def _new_request_id() -> str:
    # 12 hex символов — компактно для логов, достаточная уникальность для
    # дедупликации внутри одной минуты. Полный UUID можно прокинуть от шлюза.
    return uuid.uuid4().hex[:12]


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        incoming = request.headers.get(_REQ_ID_HEADER)
        rid = incoming if incoming else _new_request_id()
        token = request_id_var.set(rid)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            # Не логируем сам /metrics — Prometheus скрапит часто, шум большой.
            path = request.url.path
            if path != "/metrics":
                logger.info(
                    "http_request",
                    method=request.method,
                    path=path,
                    status=status_code,
                    duration_ms=round(duration_ms, 2),
                    client=request.client.host if request.client else None,
                )
            request_id_var.reset(token)


async def _add_request_id_header(request: Request, call_next: Any) -> Response:
    """Прокидывает X-Request-Id в ответ. Отдельным middleware, потому
    что BaseHTTPMiddleware не даёт удобно изменить заголовки ответа."""
    response: Response = await call_next(request)
    rid = request_id_var.get()
    if rid:
        response.headers[_REQ_ID_HEADER] = rid
    return response


__all__ = ["RequestIdMiddleware"]
