"""
Страница установки Bitrix24-приложения.

Bitrix24 открывает «Путь для первоначальной установки» (поле в карточке
приложения) в iframe внутри портала и шлёт POST с form-data,
содержащим авторизационные данные. Наш сценарий:

1. Сохраняем токены (access/refresh/expires/domain/member_id) в Integration.
   tenant_id оставляем NULL — это «осиротевшая» запись, которую клиент
   потом «заберёт» через POST /api/v1/integrations/bitrix24/connect,
   указав свой портал.
2. Возвращаем HTML с `BX24.installFinish()`, чтобы Bitrix24 пометил
   приложение как установленное (INSTALLED=true) — без этого события
   не идут и поллер тоже не сможет работать на тиражном приложении.

Документация:
  https://apidocs.bitrix24.ru/settings/app-installation/installation-finish.html
  https://apidocs.bitrix24.ru/api-reference/oauth/auth.html
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.db.models import (
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/install", tags=["install"])


_INSTALL_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Установка ai-message</title>
  <script src="//api.bitrix24.com/api/v1/"></script>
  <style>
    html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; }
    .wrap { max-width: 520px; margin: 60px auto; padding: 32px; background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.06); text-align: center; }
    h1 { font-size: 20px; margin: 0 0 12px; color: #0f172a; }
    p { margin: 8px 0; color: #475569; font-size: 14px; line-height: 1.5; }
    .ok { color: #059669; font-weight: 600; }
    .err { color: #b91c1c; font-weight: 600; }
    .hint { color: #94a3b8; font-size: 12px; margin-top: 18px; }
    .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid #cbd5e1; border-top-color: #3a66f5; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: -3px; margin-right: 6px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>ai-message</h1>
    <p id="status"><span class="spinner"></span>Завершаем установку…</p>
    <p class="hint" id="next">__NEXT_HINT__</p>
  </div>
  <script>
    (function () {
      var el = document.getElementById('status');
      function done(msg, cls) { el.innerHTML = '<span class="' + cls + '">' + msg + '</span>'; }

      if (typeof BX24 === 'undefined') {
        done('Не удалось загрузить BX24 SDK — откройте страницу из интерфейса Битрикс24.', 'err');
        return;
      }
      try {
        BX24.init(function () {
          try {
            BX24.installFinish();
            done('✓ Приложение установлено. Окно можно закрыть.', 'ok');
          } catch (e) {
            done('Ошибка installFinish: ' + (e && e.message ? e.message : e), 'err');
          }
        });
      } catch (e) {
        done('Ошибка инициализации BX24: ' + (e && e.message ? e.message : e), 'err');
      }
    })();
  </script>
</body>
</html>
"""


def _new_id() -> str:
    return f"b24_{secrets.token_urlsafe(8).lower()}"


def _form_value(form: dict, *keys: str) -> str | None:
    for k in keys:
        v = form.get(k)
        if v not in (None, ""):
            return str(v)
    return None


async def _save_install_tokens(session: AsyncSession, form: dict) -> None:
    """
    B24 шлёт в install-handler:
      AUTH_ID         — access_token
      REFRESH_ID      — refresh_token
      AUTH_EXPIRES    — секунд до истечения access (число строкой)
      DOMAIN          — домен портала, e.g. b24-xyz.bitrix24.ru
      member_id       — идентификатор портала B24
      APP_SID, PROTOCOL, LANG — служебные
      application_token — токен для проверки последующих событий

    Поля в форме именуются в верхнем регистре (AUTH_ID), но на всякий
    случай поддерживаем и нижний (auth_id).
    """
    access = _form_value(form, "AUTH_ID", "auth_id", "access_token")
    refresh = _form_value(form, "REFRESH_ID", "refresh_id", "refresh_token")
    domain = _form_value(form, "DOMAIN", "domain")
    member_id = _form_value(form, "member_id", "MEMBER_ID")
    expires_raw = _form_value(form, "AUTH_EXPIRES", "expires_in")

    if not (access and refresh and (domain or member_id)):
        logger.warning(
            "install: пропускаем — недостаточно данных в форме (access=%s domain=%s member=%s)",
            bool(access),
            domain,
            member_id,
        )
        return

    expires_in = 3600
    if expires_raw and expires_raw.isdigit():
        expires_in = int(expires_raw)
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

    # Ищем по member_id (стабильный идентификатор) либо по domain.
    integration: Integration | None = None
    if member_id:
        integration = (
            await session.execute(
                select(Integration).where(Integration.member_id == member_id).limit(1)
            )
        ).scalar_one_or_none()
    if not integration and domain:
        integration = (
            await session.execute(
                select(Integration).where(Integration.domain == domain).limit(1)
            )
        ).scalar_one_or_none()

    if integration:
        integration.access_token = access
        integration.refresh_token = refresh
        integration.expires_at = expires_at
        if domain:
            integration.domain = domain
        if member_id:
            integration.member_id = member_id
        integration.status = IntegrationStatus.connected
        logger.info(
            "install: обновлены токены integration=%s domain=%s member=%s tenant=%s",
            integration.id,
            integration.domain,
            integration.member_id,
            integration.tenant_id,
        )
    else:
        integration = Integration(
            id=_new_id(),
            tenant_id=None,  # будет привязан клиентом через /connect
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label=domain or member_id or "Bitrix24",
            domain=domain or "",
            status=IntegrationStatus.connected,
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            member_id=member_id,
        )
        session.add(integration)
        logger.info(
            "install: создана новая pending-интеграция id=%s domain=%s member=%s",
            integration.id,
            integration.domain,
            integration.member_id,
        )

    await session.commit()


@router.post("/bitrix24", response_class=HTMLResponse)
async def bitrix24_install_post(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    form: dict = {}
    try:
        form = dict(await request.form())
        await _save_install_tokens(session, form)
    except Exception as exc:  # noqa: BLE001
        logger.exception("install handler error: %s", exc)

    domain = _form_value(form, "DOMAIN")
    next_hint = (
        f'Вернитесь в ai-message и подключите портал «{domain}» по его доменному имени.'
        if domain
        else "Вернитесь в ai-message и подключите ваш портал по его доменному имени."
    )
    html = _INSTALL_HTML.replace("__NEXT_HINT__", next_hint)
    headers = {
        "X-Frame-Options": "ALLOWALL",
        "Content-Security-Policy": "frame-ancestors *",
        "Cache-Control": "no-store",
    }
    return HTMLResponse(content=html, headers=headers)


@router.get("/bitrix24", response_class=HTMLResponse)
async def bitrix24_install_get() -> HTMLResponse:
    # GET без формы — служебная страница (например, открыть для проверки).
    html = _INSTALL_HTML.replace(
        "__NEXT_HINT__",
        "Эта страница вызывается Bitrix24 автоматически при установке приложения.",
    )
    headers = {
        "X-Frame-Options": "ALLOWALL",
        "Content-Security-Policy": "frame-ancestors *",
        "Cache-Control": "no-store",
    }
    return HTMLResponse(content=html, headers=headers)
