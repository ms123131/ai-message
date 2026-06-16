"""OpenAI-compatible провайдер. Один на всех openai-совместимых API:
Groq, OpenAI, OpenRouter, Together, DeepSeek, VseGPT, локальные сервера
(vLLM, llama.cpp в openai-compat режиме) и т.д.

Различия — только `base_url`, ключ и модель. Формат запроса/ответа
одинаковый: POST /chat/completions, schema OpenAI Chat Completions.

Документация: https://platform.openai.com/docs/api-reference/chat/create
Groq: https://console.groq.com/docs/api-reference#chat-create
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

# Удобные пресеты base_url для документации/диагностики.
PRESETS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "together": "https://api.together.xyz/v1",
}


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"
    default_model = "gpt-4o-mini"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        default_model: str | None = None,
        provider_name: str = "openai_compat",
        proxy: str | None = None,
    ) -> None:
        if not api_key:
            raise LLMError(f"{provider_name}: API key is empty")
        if not base_url:
            raise LLMError(f"{provider_name}: base_url is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        if default_model:
            self.default_model = default_model
        self.name = provider_name
        # proxy задаётся, когда egress кластера геоблокирует провайдера (Groq и
        # т.п. фильтруют RU-IP). Тот же SOCKS5 Xray, что и для Telegram — см.
        # LLM_PROXY_URL / telegram_proxy_*. None => прямое соединение.
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            proxy=proxy or None,
        )

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout: float = 30.0,  # noqa: ASYNC109
    ) -> LLMResponse:
        payload = {
            "model": model or self.default_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

        try:
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"{self.name} timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"{self.name} network error: {exc}") from exc

        if resp.status_code >= 500 or resp.status_code == 429:
            raise LLMUnavailableError(
                f"{self.name} {resp.status_code}: {resp.text[:300]}"
            )
        if resp.status_code >= 400:
            raise LLMError(f"{self.name} {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"{self.name}: empty choices in response")
        first = choices[0]
        message = first.get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=data.get("model", payload["model"]),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            finish_reason=first.get("finish_reason"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()
