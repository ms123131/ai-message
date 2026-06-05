"""Наблюдаемость: структурированные логи, request_id, Prometheus.

Внутреннее API:
- `setup_logging()` — однократная инициализация structlog (вызывается из main).
- `get_logger(name)` — фабрика структурированных логгеров для модулей.
- `RequestIdMiddleware` — генерирует/прокидывает X-Request-Id, кладёт в
  contextvars для structlog.
"""

from app.observability.logging import get_logger, setup_logging
from app.observability.middleware import RequestIdMiddleware

__all__ = ["RequestIdMiddleware", "get_logger", "setup_logging"]
