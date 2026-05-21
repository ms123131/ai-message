"""Тесты LLM-резюме (фаза 6.3)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
    Message,
    SenderType,
)
from app.db.session import AsyncSessionLocal
from app.integrations.llm.base import LLMMessage, LLMResponse


async def _seed_conversation(tenant_id: str, n_messages: int = 4) -> tuple[str, str]:
    integration_id = f"intg_sum_{secrets.token_urlsafe(4)}"
    conv_id = f"cnv_sum_{secrets.token_urlsafe(4)}"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Sum",
                domain="sum.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-sum",
                channel=ConversationChannel.whatsapp,
                contact_name="Test Client",
                status=ConversationStatus.open,
            )
        )
        for i in range(n_messages):
            sender = SenderType.client if i % 2 == 0 else SenderType.agent
            session.add(
                Message(
                    id=f"m_sum_{i}_{secrets.token_urlsafe(3)}",
                    conversation_id=conv_id,
                    sender_type=sender,
                    text=f"Сообщение {i} от {sender.value}",
                    sent_at=now + timedelta(minutes=i),
                )
            )
        await session.commit()
    return integration_id, conv_id


class _FakeLLM:
    """Минимальный заглушка LLMProvider для smart-вызовов."""

    name = "fake-smart"
    default_model = "fake-haiku"

    def __init__(self, content: str = "• Клиент задал вопрос\n• Оператор ответил\n• Решено"):
        self.content = content
        self.calls: list[list[LLMMessage]] = []

    async def chat(self, messages, **kwargs):  # noqa: ANN001
        self.calls.append(list(messages))
        return LLMResponse(content=self.content, model=self.default_model)

    async def aclose(self):
        pass


@pytest.fixture
async def with_fake_smart(monkeypatch):
    from app.integrations import llm as llm_pkg
    from app.integrations.llm import factory

    fake = _FakeLLM()

    def _get(kind="fast"):
        return fake

    monkeypatch.setattr(factory, "get_llm", _get)
    monkeypatch.setattr(llm_pkg, "get_llm", _get)
    # И в модуле, где импортирован напрямую
    from app.nlp import summary as summary_mod

    monkeypatch.setattr(summary_mod, "get_llm", _get)
    return fake


@pytest.mark.asyncio
async def test_summarize_conversation_writes_fields(
    client, auth_tenant_id, with_fake_smart
):
    _, conv_id = await _seed_conversation(auth_tenant_id, n_messages=6)

    from app.nlp.summary import summarize_conversation

    async with AsyncSessionLocal() as session:
        result = await summarize_conversation(session, conv_id)
        await session.commit()

    assert result is not None
    summary, msgs_count, model = result
    assert "Клиент" in summary
    assert msgs_count == 6
    assert model == "fake-haiku"

    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        assert conv.summary == summary
        assert conv.summary_messages_count == 6
        assert conv.summary_model == "fake-haiku"
        assert conv.summary_at is not None


@pytest.mark.asyncio
async def test_summarize_empty_conversation_returns_none(
    client, auth_tenant_id, with_fake_smart
):
    _, conv_id = await _seed_conversation(auth_tenant_id, n_messages=0)
    from app.nlp.summary import summarize_conversation

    async with AsyncSessionLocal() as session:
        result = await summarize_conversation(session, conv_id)
        await session.commit()

    assert result is None


@pytest.mark.asyncio
async def test_summarize_endpoint_enqueues_job(client, auth_tenant_id, _stub_arq_pool):
    _, conv_id = await _seed_conversation(auth_tenant_id, n_messages=2)

    resp = await client.post(f"/api/v1/conversations/{conv_id}/summarize")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["conversation_id"] == conv_id

    names = [name for name, _, _ in _stub_arq_pool.enqueued]
    assert "summarize_conversation_task" in names


@pytest.mark.asyncio
async def test_summarize_endpoint_404_for_other_tenant(client, auth_tenant_id):
    """Чужой диалог нельзя резюмировать."""
    # Создаём интеграцию с другим tenant_id
    other_tenant = "tenant_other"
    async with AsyncSessionLocal() as session:
        from app.db.models import Tenant

        session.add(Tenant(id=other_tenant, name="Other"))
        await session.commit()
    _, foreign_conv_id = await _seed_conversation(other_tenant, n_messages=2)

    resp = await client.post(
        f"/api/v1/conversations/{foreign_conv_id}/summarize"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_conversation_out_includes_summary(client, auth_tenant_id):
    _, conv_id = await _seed_conversation(auth_tenant_id, n_messages=3)
    # Предзаписываем summary напрямую в БД
    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        conv.summary = "• Тест • Сводка • Готово"
        conv.summary_model = "fake-haiku"
        conv.summary_messages_count = 3
        conv.summary_at = datetime.now(UTC)
        await session.commit()

    resp = await client.get(f"/api/v1/conversations/{conv_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["summary"] == "• Тест • Сводка • Готово"
    assert body["summary_messages_count"] == 3
    assert body["summary_model"] == "fake-haiku"
    assert body["summary_at"] is not None
