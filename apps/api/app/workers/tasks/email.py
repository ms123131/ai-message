"""arq-задачи отправки транзакционных писем (verify / reset).

Письма уходят из воркера, а не из API-запроса: отправка по SMTP может быть
медленной/нестабильной, а arq даёт ретраи. Рендер — тоже здесь, чтобы в
очередь Redis шёл компактный payload (адрес + имя + ссылка), а не готовый HTML.
"""

from __future__ import annotations

import logging
from typing import Any

from app.email.mailer import send_message
from app.email.render import render_reset, render_verification

logger = logging.getLogger(__name__)


async def send_verification_email(
    ctx: dict[str, Any],  # noqa: ARG001 — сигнатура arq-таски
    to: str,
    user_name: str | None,
    verify_url: str,
) -> dict[str, Any]:
    subject, html, text = render_verification(user_name, verify_url)
    sent = await send_message(to=to, subject=subject, html=html, text=text)
    return {"status": "sent" if sent else "skipped_no_smtp", "to": to}


async def send_password_reset_email(
    ctx: dict[str, Any],  # noqa: ARG001 — сигнатура arq-таски
    to: str,
    user_name: str | None,
    reset_url: str,
) -> dict[str, Any]:
    subject, html, text = render_reset(user_name, reset_url)
    sent = await send_message(to=to, subject=subject, html=html, text=text)
    return {"status": "sent" if sent else "skipped_no_smtp", "to": to}
