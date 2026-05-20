"""Anthropic Claude через REST API (без официального SDK).

Используем httpx напрямую: меньше зависимостей, проще мокать в тестах,
поведение одинаковое с openai-compat провайдером. Если позже понадобится
prompt caching / extended thinking — добавляем нужные поля в payload
без смены интерфейса.

Endpoint: POST https://api.anthropic.com/v1/messages
Документация: https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import httpx

from app.integrations.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMTimeoutError,
    LLMUnavailableError,
)

ANTHROPIC_VERSION = "2023-06-01"


class ClaudeProvider(LLMProvider):
    name = "claude"
    # Безопасный дефолт — самый дешёвый Haiku 4.5. Реальную модель пользователь
    # указывает в settings.llm_*_model.
    default_model = "claude-haiku-4-5-20251001"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com",
        default_model: str | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("Claude API key is empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        if default_model:
            self.default_model = default_model
        # Один httpx-клиент на провайдер — переиспользует TCP-соединения.
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 30.0,  # noqa: ASYNC109
    ) -> LLMResponse:
        # Anthropic API отделяет system от messages.
        system_parts = [m.content for m in messages if m.role == "system"]
        chat_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        if not chat_messages:
            raise LLMError("Claude: messages must contain at least one user/assistant turn")

        payload: dict = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        try:
            resp = await self._client.post(
                f"{self._base_url}/v1/messages",
                json=payload,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Claude timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"Claude network error: {exc}") from exc

        if resp.status_code >= 500 or resp.status_code == 429:
            raise LLMUnavailableError(
                f"Claude {resp.status_code}: {resp.text[:300]}"
            )
        if resp.status_code >= 400:
            raise LLMError(f"Claude {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        # content — массив блоков; берём только text-блоки (tool_use позже).
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = data.get("usage") or {}
        return LLMResponse(
            content=text,
            model=data.get("model", payload["model"]),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            finish_reason=data.get("stop_reason"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
