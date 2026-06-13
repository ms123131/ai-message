"""Низкоуровневая отправка письма через SMTP (aiosmtplib).

Письмо — всегда multipart/alternative (text + html): plain-text часть
обязательна, она заметно улучшает спам-скор и нужна текстовым клиентам.
Если SMTP не настроен (smtp_host пуст) — письмо логируется и пропускается,
чтобы dev/test работали без почтового сервера.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_message(*, to: str, subject: str, html: str, text: str) -> bool:
    """Отправляет письмо. Возвращает True если ушло, False если SMTP отключён."""
    settings = get_settings()
    if not settings.smtp_host:
        logger.warning(
            "SMTP не настроен (SMTP_HOST пуст) — письмо «%s» на %s НЕ отправлено",
            subject,
            to,
        )
        return False

    from_addr = settings.email_from or settings.smtp_user or "noreply@localhost"
    from_domain = from_addr.split("@")[-1]

    msg = EmailMessage()
    msg["From"] = formataddr((settings.email_from_name, from_addr))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=from_domain)
    # List-Unsubscribe полезен даже для транзакционных писем — снижает
    # вероятность пометки «спам» у Gmail/Mail.ru.
    msg["List-Unsubscribe"] = f"<mailto:{from_addr}>"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    mode = settings.smtp_tls_mode
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        use_tls=(mode == "ssl"),
        start_tls=(mode == "starttls"),
    )
    logger.info("письмо «%s» отправлено на %s", subject, to)
    return True
