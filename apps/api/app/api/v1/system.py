"""Системные эндпоинты для фронта: статус доступности AI-функций и т.п."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db.models import User as UserModel

router = APIRouter(prefix="/system", tags=["system"])


class LLMStatus(BaseModel):
    fast_available: bool
    smart_available: bool


def _provider_available(provider: str | None, api_key: str | None) -> bool:
    """Доступным считаем непустого провайдера с настроенным ключом.

    null/none/off/disabled — отключен; claude/openai-compat без ключа
    тоже трактуются как недоступные, чтобы UI мог честно сказать
    «настройте провайдера».
    """
    p = (provider or "null").lower()
    if p in ("null", "", "none", "off", "disabled"):
        return False
    return bool(api_key)


@router.get("/llm-status", response_model=LLMStatus)
async def llm_status(
    _user: UserModel = Depends(get_current_user),
) -> LLMStatus:
    """Возвращает доступность fast/smart LLM-провайдеров.

    Только булевые флаги — никаких ключей и base_url. Фронт по ним рисует
    баннер «AI-фичи отключены» и блокирует кнопку «Запустить анализ».
    """
    s = get_settings()
    return LLMStatus(
        fast_available=_provider_available(s.llm_fast_provider, s.llm_fast_api_key),
        smart_available=_provider_available(s.llm_smart_provider, s.llm_smart_api_key),
    )
