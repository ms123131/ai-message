"""Фабрика LLM-провайдеров.

Принцип: код в воркере/api зовёт `await get_llm("fast")` или `("smart")`,
получает готовый `LLMProvider` и работает через единый интерфейс. Какой
SDK и какая модель — решает конфиг.

Кэшируем инстансы per-event-loop, чтобы переиспользовать httpx-клиент
(keep-alive, TCP-соединения). В тестах сбрасывается через `reset_cache()`.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.config import get_settings
from app.integrations.llm.base import LLMError, LLMProvider
from app.integrations.llm.claude import ClaudeProvider
from app.integrations.llm.null import NullLLMProvider
from app.integrations.llm.openai_compat import PRESETS, OpenAICompatProvider

logger = logging.getLogger(__name__)

LLMKind = Literal["fast", "smart"]

_cache: dict[LLMKind, LLMProvider] = {}


def _build_provider(
    *,
    provider: str,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    proxy: str | None = None,
) -> LLMProvider:
    provider = (provider or "null").lower()

    if provider in ("null", "", "none", "off", "disabled"):
        return NullLLMProvider()

    if provider == "claude":
        if not api_key:
            raise LLMError("LLM provider=claude, но API-ключ не задан")
        return ClaudeProvider(
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com",
            default_model=model,
        )

    # OpenAI-compatible семейство: достаточно знать base_url.
    if provider in PRESETS:
        if not api_key:
            raise LLMError(f"LLM provider={provider}, но API-ключ не задан")
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=base_url or PRESETS[provider],
            default_model=model,
            provider_name=provider,
            proxy=proxy,
        )

    # Универсальный «своя openai-compat установка» (VseGPT, vLLM, прокси).
    if provider in ("openai_compat", "custom"):
        if not base_url:
            raise LLMError(
                "LLM provider=openai_compat требует LLM_*_BASE_URL"
            )
        if not api_key:
            raise LLMError("LLM provider=openai_compat, но API-ключ не задан")
        return OpenAICompatProvider(
            api_key=api_key,
            base_url=base_url,
            default_model=model,
            provider_name="openai_compat",
            proxy=proxy,
        )

    raise LLMError(f"Неизвестный LLM-провайдер: {provider!r}")


def get_llm(kind: LLMKind = "fast") -> LLMProvider:
    """Возвращает (и кэширует) LLM-провайдера выбранного назначения."""
    if kind in _cache:
        return _cache[kind]

    settings = get_settings()
    if kind == "fast":
        provider = _build_provider(
            provider=settings.llm_fast_provider,
            model=settings.llm_fast_model,
            api_key=settings.llm_fast_api_key,
            base_url=settings.llm_fast_base_url,
            proxy=settings.llm_proxy_url,
        )
    elif kind == "smart":
        provider = _build_provider(
            provider=settings.llm_smart_provider,
            model=settings.llm_smart_model,
            api_key=settings.llm_smart_api_key,
            base_url=settings.llm_smart_base_url,
            proxy=settings.llm_proxy_url,
        )
    else:  # pragma: no cover — typing-проверка ловит раньше
        raise LLMError(f"Неизвестный LLMKind: {kind!r}")

    _cache[kind] = provider
    return provider


async def reset_cache() -> None:
    """Сбрасывает кэш + корректно закрывает httpx-клиенты. Для тестов и shutdown."""
    for provider in list(_cache.values()):
        try:
            await provider.aclose()
        except Exception as exc:  # noqa: BLE001 — shutdown best-effort
            logger.warning("aclose failed for %s: %s", provider.name, exc)
    _cache.clear()
