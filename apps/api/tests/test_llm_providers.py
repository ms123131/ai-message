"""Тесты LLM-абстракции: null, claude, openai-compat, factory.

Сетевые вызовы мокаются через httpx.MockTransport: каждый тест собирает
ответ вручную и проверяет, что наш код корректно его парсит и маппит
ошибки в LLMError.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.integrations.llm import (
    LLMError,
    LLMMessage,
    LLMTimeoutError,
    LLMUnavailableError,
    get_llm,
    reset_cache,
)
from app.integrations.llm.claude import ClaudeProvider
from app.integrations.llm.null import NullLLMProvider
from app.integrations.llm.openai_compat import OpenAICompatProvider


def _patch_client(provider, handler):
    """Подменяем httpx.AsyncClient внутри провайдера на mock-transport."""
    transport = httpx.MockTransport(handler)
    provider._client = httpx.AsyncClient(transport=transport)


@pytest.fixture
def reset_llm(monkeypatch):
    """Сбрасывает settings + LLM-кэш до/после теста."""
    import asyncio

    asyncio.get_event_loop().run_until_complete(reset_cache()) if False else None
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_null_provider_returns_stub_without_network():
    p = NullLLMProvider()
    resp = await p.chat([LLMMessage(role="user", content="Hello there")])
    assert "Hello there" in resp.content
    assert resp.model == "null"
    assert resp.input_tokens == 0


@pytest.mark.asyncio
async def test_claude_provider_happy_path():
    p = ClaudeProvider(api_key="test-key", default_model="claude-haiku-4-5-20251001")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["anthropic-version"]
        body = request.read()
        # system отделён от messages
        import json as _json

        payload = _json.loads(body)
        assert payload["system"] == "you are helpful"
        assert payload["messages"] == [{"role": "user", "content": "ping"}]
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "model": "claude-haiku-4-5-20251001",
                "content": [{"type": "text", "text": "pong"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )

    _patch_client(p, handler)
    resp = await p.chat(
        [
            LLMMessage(role="system", content="you are helpful"),
            LLMMessage(role="user", content="ping"),
        ]
    )
    assert resp.content == "pong"
    assert resp.input_tokens == 5
    assert resp.output_tokens == 2
    assert resp.finish_reason == "end_turn"
    await p.aclose()


@pytest.mark.asyncio
async def test_claude_5xx_maps_to_unavailable():
    p = ClaudeProvider(api_key="test-key")
    _patch_client(p, lambda req: httpx.Response(503, text="overloaded"))
    with pytest.raises(LLMUnavailableError):
        await p.chat([LLMMessage(role="user", content="x")])
    await p.aclose()


@pytest.mark.asyncio
async def test_claude_429_is_unavailable_not_error():
    p = ClaudeProvider(api_key="test-key")
    _patch_client(p, lambda req: httpx.Response(429, text="rate limit"))
    with pytest.raises(LLMUnavailableError):
        await p.chat([LLMMessage(role="user", content="x")])
    await p.aclose()


@pytest.mark.asyncio
async def test_claude_4xx_maps_to_error():
    p = ClaudeProvider(api_key="test-key")
    _patch_client(p, lambda req: httpx.Response(400, text="bad request"))
    with pytest.raises(LLMError) as excinfo:
        await p.chat([LLMMessage(role="user", content="x")])
    # Это не LLMUnavailableError — 400 не retryable
    assert not isinstance(excinfo.value, LLMUnavailableError)
    await p.aclose()


@pytest.mark.asyncio
async def test_claude_timeout_maps_to_timeout_error():
    p = ClaudeProvider(api_key="test-key")

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=req)

    _patch_client(p, handler)
    with pytest.raises(LLMTimeoutError):
        await p.chat([LLMMessage(role="user", content="x")])
    await p.aclose()


@pytest.mark.asyncio
async def test_claude_requires_user_message():
    p = ClaudeProvider(api_key="test-key")
    with pytest.raises(LLMError, match="at least one"):
        await p.chat([LLMMessage(role="system", content="only system")])


@pytest.mark.asyncio
async def test_openai_compat_groq_happy_path():
    p = OpenAICompatProvider(
        api_key="gsk_test",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        provider_name="groq",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer gsk_test"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "llama-3.3-70b-versatile",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    _patch_client(p, handler)
    resp = await p.chat([LLMMessage(role="user", content="hello")])
    assert resp.content == "hi"
    assert resp.model == "llama-3.3-70b-versatile"
    assert resp.input_tokens == 3
    assert resp.output_tokens == 1
    assert resp.finish_reason == "stop"
    await p.aclose()


@pytest.mark.asyncio
async def test_openai_compat_empty_choices_raises():
    p = OpenAICompatProvider(
        api_key="k", base_url="https://example.com/v1", provider_name="custom"
    )
    _patch_client(p, lambda req: httpx.Response(200, json={"choices": []}))
    with pytest.raises(LLMError, match="empty choices"):
        await p.chat([LLMMessage(role="user", content="x")])
    await p.aclose()


@pytest.mark.asyncio
async def test_factory_returns_null_by_default(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.delenv("LLM_FAST_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_SMART_PROVIDER", raising=False)
    assert get_llm("fast").name == "null"
    assert get_llm("smart").name == "null"
    await reset_cache()


@pytest.mark.asyncio
async def test_factory_builds_groq_provider(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_FAST_PROVIDER", "groq")
    monkeypatch.setenv("LLM_FAST_API_KEY", "gsk_xxx")
    monkeypatch.setenv("LLM_FAST_MODEL", "llama-3.3-70b-versatile")

    llm = get_llm("fast")
    assert llm.name == "groq"
    assert llm.default_model == "llama-3.3-70b-versatile"
    await reset_cache()


@pytest.mark.asyncio
async def test_factory_builds_claude_provider(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_SMART_PROVIDER", "claude")
    monkeypatch.setenv("LLM_SMART_API_KEY", "sk-ant-xxx")

    llm = get_llm("smart")
    assert llm.name == "claude"
    await reset_cache()


@pytest.mark.asyncio
async def test_factory_rejects_unknown_provider(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_FAST_PROVIDER", "skynet")
    monkeypatch.setenv("LLM_FAST_API_KEY", "x")
    with pytest.raises(LLMError, match="Неизвестный"):
        get_llm("fast")
    await reset_cache()


@pytest.mark.asyncio
async def test_factory_requires_api_key_for_real_providers(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_FAST_PROVIDER", "groq")
    monkeypatch.delenv("LLM_FAST_API_KEY", raising=False)
    with pytest.raises(LLMError, match="API-ключ"):
        get_llm("fast")
    await reset_cache()


@pytest.mark.asyncio
async def test_factory_caches_instance(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_FAST_PROVIDER", "null")
    a = get_llm("fast")
    b = get_llm("fast")
    assert a is b
    await reset_cache()


@pytest.mark.asyncio
async def test_factory_openai_compat_requires_base_url(monkeypatch):
    await reset_cache()
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_FAST_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_FAST_API_KEY", "k")
    monkeypatch.delenv("LLM_FAST_BASE_URL", raising=False)
    with pytest.raises(LLMError, match="BASE_URL"):
        get_llm("fast")
    await reset_cache()
