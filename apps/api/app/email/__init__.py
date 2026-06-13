"""Транзакционная почта: одноразовые токены, рендер писем, SMTP-отправка.

Подтверждение email (Hard-confirm) и сброс пароля. Отправка идёт через
arq-воркер (app.workers.tasks.email), здесь — примитивы.
"""

from app.email.mailer import send_message
from app.email.render import render_reset, render_verification
from app.email.tokens import consume_token, issue_token

__all__ = [
    "send_message",
    "render_verification",
    "render_reset",
    "issue_token",
    "consume_token",
]
