"""Конфигурация structlog → JSON-логи + поддержка request_id.

В dev (`APP_ENV=development`) рендерим логи человекочитаемо
(ConsoleRenderer), в проде — JSON через JSONRenderer. stdlib-логгеры
(SQLAlchemy, httpx, uvicorn) бриджуются на тот же конвейер через
ProcessorFormatter, чтобы лог-сообщения от FastAPI/uvicorn тоже
выходили JSON-строками и содержали request_id из contextvars.

`request_id_var` — публичный ContextVar; middleware и таски пишут в
него UUID запроса/джоба, structlog подхватывает через
`merge_contextvars`-processor.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# Публичный contextvar — middleware кладёт сюда X-Request-Id, structlog
# подмешивает в каждое сообщение через merge_contextvars.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _add_request_id(_logger: Any, _name: str, event_dict: dict) -> dict:
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def setup_logging(*, json_logs: bool, level: str = "INFO") -> None:
    """Инициализирует structlog + bridge на stdlib. Идемпотентно."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib-логгеров (uvicorn, sqlalchemy, httpx) на тот же
    # рендер. ProcessorFormatter принимает уже-обработанный event_dict
    # от foreign-loggers и прогоняет финальный рендер.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Чистим прежние basicConfig-хендлеры, чтобы не было дубль-вывода.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn пишет в свои логгеры — подменяем им хендлеры.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False


def get_logger(name: str | None = None) -> Any:
    """Возвращает structlog-логгер с привязанным `logger`-полем."""
    return structlog.get_logger(name)


__all__ = ["get_logger", "request_id_var", "setup_logging"]
