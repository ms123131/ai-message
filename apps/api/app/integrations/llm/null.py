"""Null-провайдер. Используется когда LLM-фичи отключены или в тестах.

Возвращает детерминированную заглушку и не делает сетевых вызовов.
Это безопасный дефолт: если в проде неправильно сконфигурирован
провайдер, мы получаем заглушки, а не падающие запросы.
"""

from __future__ import annotations

from app.integrations.llm.base import LLMMessage, LLMProvider, LLMResponse


class NullLLMProvider(LLMProvider):
    name = "null"
    default_model = "null"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,  # noqa: ARG002
        temperature: float = 0.0,  # noqa: ARG002
        timeout: float = 30.0,  # noqa: ARG002, ASYNC109
    ) -> LLMResponse:
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            "",
        )
        return LLMResponse(
            content=f"[null-llm] {last_user[:80]}",
            model=model or self.default_model,
            input_tokens=0,
            output_tokens=0,
            finish_reason="stop",
        )
