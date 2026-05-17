"""
Страница установки Bitrix24-приложения.

Bitrix24 открывает «Путь для первоначальной установки» (поле в карточке
локального приложения) в iframe внутри портала и шлёт POST с form-data
авторизации. Наша задача — вызвать BX24.installFinish() в iframe, после
чего Bitrix24 пометит приложение как установленное (INSTALLED=true) и начнёт
доставлять события на event.bind-обработчик.

Документация:
  https://apidocs.bitrix24.ru/settings/app-installation/installation-finish.html
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/install", tags=["install"])

# Минимальная HTML-страница для iframe. Не нужно сохранять токены — у нас есть
# свой OAuth-flow через /integrations/bitrix24/oauth/exchange. Главное — закрыть
# установку через BX24.installFinish() и показать понятное сообщение.
_INSTALL_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Установка ai-message</title>
  <script src="//api.bitrix24.com/api/v1/"></script>
  <style>
    html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f8fafc; }
    .wrap { max-width: 480px; margin: 60px auto; padding: 32px; background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.06); text-align: center; }
    h1 { font-size: 20px; margin: 0 0 12px; color: #0f172a; }
    p { margin: 8px 0; color: #475569; font-size: 14px; line-height: 1.5; }
    .ok { color: #059669; font-weight: 600; }
    .err { color: #b91c1c; font-weight: 600; }
    .spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid #cbd5e1; border-top-color: #3a66f5; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: -3px; margin-right: 6px; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>ai-message</h1>
    <p id="status"><span class="spinner"></span>Завершаем установку…</p>
    <p style="font-size:12px;color:#94a3b8;margin-top:24px;">
      Окно можно закрыть после появления зелёной отметки.
    </p>
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
            done('✓ Установка завершена. Приложение готово к работе.', 'ok');
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


@router.post("/bitrix24", response_class=HTMLResponse)
@router.get("/bitrix24", response_class=HTMLResponse)
async def bitrix24_install() -> HTMLResponse:
    # Снимаем X-Frame-Options для этого ответа — страница должна открываться
    # в iframe внутри портала Bitrix24.
    headers = {
        "X-Frame-Options": "ALLOWALL",
        "Content-Security-Policy": "frame-ancestors *",
        "Cache-Control": "no-store",
    }
    return HTMLResponse(content=_INSTALL_HTML, headers=headers)
