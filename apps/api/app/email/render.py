"""Рендер транзакционных писем: брендированный HTML + plain-text.

Table-based вёрстка с инлайн-стилями (требование почтовых клиентов,
особенно Outlook). Каждое письмо возвращается тройкой (subject, html, text).
Палитра — бренд ai-message (brand-500 #3a66f5 / brand-600 #2748db), шрифт
Inter с системными фолбэками. HTML экранируется для пользовательских данных.
"""

from __future__ import annotations

import html as _html

BRAND = "#2748db"
BRAND_LIGHT = "#3a66f5"
BG = "#f4f6fb"
TEXT = "#1f2937"
MUTED = "#6b7280"
FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,"
    "Helvetica,Arial,sans-serif"
)


def _layout(
    *,
    preheader: str,
    heading: str,
    intro: str,
    cta_text: str,
    cta_url: str,
    after: str,
    note: str,
) -> str:
    """Собирает финальный HTML письма из фрагментов (уже экранированных)."""
    return f"""<!DOCTYPE html>
<html lang="ru" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{heading}</title>
</head>
<body style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e5e9f2;">
<tr><td style="padding:28px 32px 8px 32px;font-family:{FONT};">
<span style="font-size:20px;font-weight:700;color:{BRAND};letter-spacing:-0.3px;">ai-message</span>
</td></tr>
<tr><td style="padding:8px 32px 0 32px;font-family:{FONT};">
<h1 style="margin:0 0 12px 0;font-size:22px;line-height:1.3;color:{TEXT};font-weight:700;">{heading}</h1>
<p style="margin:0 0 20px 0;font-size:15px;line-height:1.6;color:{TEXT};">{intro}</p>
</td></tr>
<tr><td align="center" style="padding:4px 32px 8px 32px;">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td align="center" bgcolor="{BRAND}" style="border-radius:10px;">
<a href="{cta_url}" target="_blank" style="display:inline-block;padding:13px 28px;font-family:{FONT};font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:10px;">{cta_text}</a>
</td></tr></table>
</td></tr>
<tr><td style="padding:16px 32px 0 32px;font-family:{FONT};">
<p style="margin:0 0 8px 0;font-size:13px;line-height:1.6;color:{MUTED};">{after}</p>
<p style="margin:0 0 4px 0;font-size:13px;line-height:1.6;color:{MUTED};">Если кнопка не работает, скопируйте ссылку в браузер:</p>
<p style="margin:0 0 20px 0;font-size:13px;line-height:1.5;word-break:break-all;"><a href="{cta_url}" target="_blank" style="color:{BRAND_LIGHT};">{cta_url}</a></p>
</td></tr>
<tr><td style="padding:0 32px 28px 32px;font-family:{FONT};border-top:1px solid #eef1f7;">
<p style="margin:18px 0 0 0;font-size:12px;line-height:1.6;color:{MUTED};">{note}</p>
</td></tr>
</table>
<p style="max-width:560px;margin:18px auto 0 auto;font-family:{FONT};font-size:12px;line-height:1.5;color:#9aa3b2;text-align:center;">ai-message · анализ коммуникаций<br>Это автоматическое сообщение, отвечать на него не нужно.</p>
</td></tr>
</table>
</body>
</html>"""


def _greeting(name: str | None) -> str:
    return f"Здравствуйте, {_html.escape(name)}!" if name else "Здравствуйте!"


def render_verification(name: str | None, verify_url: str) -> tuple[str, str, str]:
    subject = "Подтвердите адрес электронной почты"
    greeting = _greeting(name)
    html = _layout(
        preheader="Остался один шаг — подтвердите почту, чтобы войти в ai-message.",
        heading="Подтвердите почту",
        intro=(
            f"{greeting} Вы создали аккаунт в ai-message. "
            "Чтобы завершить регистрацию и войти, подтвердите адрес — "
            "нажмите кнопку ниже."
        ),
        cta_text="Подтвердить почту",
        cta_url=verify_url,
        after="Ссылка действует 24 часа.",
        note=(
            "Если вы не регистрировались в ai-message, просто проигнорируйте "
            "это письмо — аккаунт без подтверждения не активируется."
        ),
    )
    text = (
        f"{greeting}\n\n"
        "Вы создали аккаунт в ai-message. Чтобы завершить регистрацию и войти, "
        "подтвердите адрес электронной почты, перейдя по ссылке:\n\n"
        f"{verify_url}\n\n"
        "Ссылка действует 24 часа.\n\n"
        "Если вы не регистрировались в ai-message, просто проигнорируйте это письмо.\n\n"
        "— ai-message"
    )
    return subject, html, text


def render_reset(name: str | None, reset_url: str) -> tuple[str, str, str]:
    subject = "Сброс пароля в ai-message"
    greeting = _greeting(name)
    html = _layout(
        preheader="Запрошен сброс пароля. Если это были не вы — проигнорируйте письмо.",
        heading="Сброс пароля",
        intro=(
            f"{greeting} Мы получили запрос на сброс пароля для вашего аккаунта "
            "ai-message. Чтобы задать новый пароль, нажмите кнопку ниже."
        ),
        cta_text="Задать новый пароль",
        cta_url=reset_url,
        after="Ссылка действует 2 часа.",
        note=(
            "Если вы не запрашивали сброс пароля, проигнорируйте это письмо — "
            "ваш текущий пароль останется без изменений."
        ),
    )
    text = (
        f"{greeting}\n\n"
        "Мы получили запрос на сброс пароля для вашего аккаунта ai-message. "
        "Чтобы задать новый пароль, перейдите по ссылке:\n\n"
        f"{reset_url}\n\n"
        "Ссылка действует 2 часа.\n\n"
        "Если вы не запрашивали сброс пароля, проигнорируйте это письмо.\n\n"
        "— ai-message"
    )
    return subject, html, text
