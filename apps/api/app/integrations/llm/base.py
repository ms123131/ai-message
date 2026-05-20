"""Общий интерфейс LLM-провайдера.

Цель — изолировать SDK конкретных вендоров (anthropic, openai, ...) за
единым API, чтобы остальной код мог просто звать `llm.chat(messages)` и
не знал, кто там под капотом. Любой провайдер должен:

1. Принимать список `LLMMessage` (наш внутренний тип, а не SDK-сообщения).
2. Возвращать `LLMResponse` с распарсенным контентом и метаданными.
3. Маппить сетевые/SDK-ошибки в `LLMError` (или подклассы) — выше по
   стеку не должно быть исключений из openai/anthropic.

Стриминг намеренно НЕ закладываем: первые сценарии (sentiment, tagging,
summary) работают по принципу «дождались полного ответа и записали». Если
понадобится — добавим `chat_stream()` отдельным методом, не ломая текущий.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LLMMessage(BaseModel):
    """Сообщение в диалоге с LLM. Минимальный набор полей."""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResponse(BaseModel):
    """Ответ LLM. `model` — фактическая модель, которая ответила (важно для логов)."""

    model_config = ConfigDict(frozen=True)

    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = Field(
        default=None,
        description="stop|length|content_filter|tool_use — нормализованное",
    )


class LLMError(Exception):
    """Базовая ошибка LLM-слоя. Всё, что выше base.py, ловит только её."""


class LLMTimeoutError(LLMError):
    """Запрос не уложился в таймаут."""


class LLMUnavailableError(LLMError):
    """5xx от провайдера, сеть, rate limit и прочее retryable."""


class LLMProvider(ABC):
    """Контракт провайдера. Каждая реализация знает про конкретный SDK."""

    #: Человекочитаемое имя — для логов и ошибок.
    name: str = "abstract"
    #: Модель по умолчанию — переопределяется конфигом, но провайдер должен иметь fallback.
    default_model: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 30.0,  # noqa: ASYNC109 — внешний HTTP-таймаут, не asyncio.timeout
    ) -> LLMResponse:
        """Синхронный (один ответ) вызов чат-модели."""

    async def aclose(self) -> None:  # noqa: B027 — намеренно опциональный hook
        """Освободить ресурсы (httpx-клиент и т.п.). По умолчанию — no-op."""
