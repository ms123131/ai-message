"""Тесты AI-ассистента «спроси свою переписку» (v1).

На SQLite vector-поиск недоступен → retrieve_context возвращает degraded,
поэтому RAG-часть проверяем на degrade-режиме, а tenant-изоляцию агрегата
«слабых мест» — напрямую на портативном ORM-пути (compute_weak_spots).
LLM мокаем фейковым smart-провайдером.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.models import (
    AiThread,
    Conversation,
    ConversationChannel,
    ConversationStatus,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
    Tenant,
    User,
)
from app.db.session import AsyncSessionLocal
from app.integrations.llm.base import LLMResponse


class _FakeSmart:
    """Фейковый smart-провайдер: запоминает последний список сообщений."""

    def __init__(self) -> None:
        self.last_messages = None

    async def chat(self, messages, **kwargs):
        self.last_messages = messages
        return LLMResponse(
            content="Рекомендация ассистента",
            model="fake-smart",
            input_tokens=42,
            output_tokens=7,
        )

    async def aclose(self) -> None:  # pragma: no cover
        pass


@pytest.fixture
def fake_smart(monkeypatch):
    fake = _FakeSmart()
    monkeypatch.setattr("app.api.v1.ai_assistant._smart_enabled", lambda: True)
    monkeypatch.setattr(
        "app.api.v1.ai_assistant.get_llm", lambda kind="smart": fake
    )
    return fake


async def test_chat_503_when_smart_disabled(client):
    # По умолчанию llm_smart_provider=null → ассистент недоступен.
    resp = await client.post("/api/v1/ai/chat", json={"message": "Привет"})
    assert resp.status_code == 503


async def test_chat_creates_thread_and_persists(client, fake_smart):
    resp = await client.post(
        "/api/v1/ai/chat", json={"message": "Какие частые темы обращений?"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["answer"] == "Рекомендация ассистента"
    # На SQLite нет vector-поиска → degraded-режим.
    assert data["degraded"] is True
    thread_id = data["thread_id"]

    # Тред содержит вопрос + ответ.
    detail = await client.get(f"/api/v1/ai/threads/{thread_id}")
    assert detail.status_code == 200
    msgs = detail.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["content"] == "Рекомендация ассистента"


async def test_chat_multiturn_includes_history(client, fake_smart):
    first = await client.post("/api/v1/ai/chat", json={"message": "Первый вопрос"})
    thread_id = first.json()["thread_id"]

    await client.post(
        "/api/v1/ai/chat",
        json={"thread_id": thread_id, "message": "Второй вопрос"},
    )
    # В промпте второго вызова должна быть история (system + прошлый Q/A + новый Q).
    roles = [m.role for m in fake_smart.last_messages]
    assert roles[0] == "system"
    assert "user" in roles[1:] and "assistant" in roles[1:]
    assert fake_smart.last_messages[-1].content == "Второй вопрос"


async def test_business_profile_roundtrip_and_in_prompt(client, fake_smart):
    put = await client.put(
        "/api/v1/ai/business-profile",
        json={"business_profile": "Продаём CRM малому бизнесу. Тон — дружелюбный."},
    )
    assert put.status_code == 200
    got = await client.get("/api/v1/ai/business-profile")
    assert "CRM малому бизнесу" in got.json()["business_profile"]

    await client.post("/api/v1/ai/chat", json={"message": "Как отвечать клиентам?"})
    system_msg = fake_smart.last_messages[0].content
    assert "CRM малому бизнесу" in system_msg


async def test_cannot_open_foreign_thread(client, fake_smart):
    # Сидим тред чужого tenant'а напрямую в БД.
    async with AsyncSessionLocal() as session:
        session.add(Tenant(id="other_tenant", name="Other"))
        session.add(
            User(
                id="other_user",
                tenant_id="other_tenant",
                email="other@example.com",
                password_hash="x",
            )
        )
        await session.flush()
        session.add(
            AiThread(
                id="ait_foreign",
                tenant_id="other_tenant",
                user_id="other_user",
                title="чужой тред",
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/ai/threads/ait_foreign")
    assert resp.status_code == 404


async def test_delete_thread(client, fake_smart):
    created = await client.post("/api/v1/ai/chat", json={"message": "вопрос"})
    thread_id = created.json()["thread_id"]
    deleted = await client.delete(f"/api/v1/ai/threads/{thread_id}")
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/ai/threads/{thread_id}")).status_code == 404


def _seed_conv(session, *, tenant_id, intg_id, conv_id, score, tags):
    session.add(
        Integration(
            id=intg_id,
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="x",
            domain="x.bitrix24.ru",
            status=IntegrationStatus.connected,
        )
    )
    session.add(
        Conversation(
            id=conv_id,
            integration_id=intg_id,
            external_id=conv_id,
            channel=ConversationChannel.telegram,
            status=ConversationStatus.open,
            sentiment_score=score,
            tags=tags,
            first_message_at=datetime.now(UTC),
        )
    )


async def test_weak_spots_is_tenant_isolated():
    from app.db.session import Base, engine
    from app.services.ai_assistant.analytics import compute_weak_spots

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        session.add(Tenant(id="t_a", name="A"))
        session.add(Tenant(id="t_b", name="B"))
        await session.flush()
        # tenant A: 1 негативный диалог с темой «оплата».
        _seed_conv(
            session, tenant_id="t_a", intg_id="i_a", conv_id="c_a",
            score=-0.8, tags=["оплата"],
        )
        # tenant B: 1 негативный диалог с темой «доставка».
        _seed_conv(
            session, tenant_id="t_b", intg_id="i_b", conv_id="c_b",
            score=-0.9, tags=["доставка"],
        )
        await session.commit()

        summary_a = await compute_weak_spots(session, "t_a")

    assert summary_a is not None
    assert "оплата" in summary_a
    # Данные tenant B не должны протекать в сводку A.
    assert "доставка" not in summary_a
    assert "всего диалогов: 1" in summary_a
