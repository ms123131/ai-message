"""Тесты бэкенд-частей фазы 6.1.1 (Sentiment UI):

- расширение ConversationListItem полем sentiment_score
- фильтр sentiment в GET /conversations
- поля sentiment_avg/_prev/_pending в GET /dashboard/overview
- новый endpoint GET /dashboard/top-negative-conversations
- GET /system/llm-status
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
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
    Sentiment,
)
from app.db.session import AsyncSessionLocal


async def _seed_with_sentiment(tenant_id: str) -> str:
    """Сидим интеграцию + 3 диалога: negative (-0.8), neutral (0.0), positive (+0.7)
    плюс один без оценки. Возвращаем integration_id.
    """
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_sent",
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="Sent",
            domain="sent.bitrix24.ru",
            status=IntegrationStatus.connected,
        )
        session.add(integration)
        await session.flush()

        now = datetime.now(UTC)
        scores = {
            "neg": -0.8,
            "neu": 0.0,
            "pos": 0.7,
            "nul": None,
        }
        for key, score in scores.items():
            session.add(
                Conversation(
                    id=f"cs_{key}",
                    integration_id=integration.id,
                    external_id=f"ext_{key}",
                    channel=ConversationChannel.whatsapp,
                    contact_name=f"Contact {key}",
                    contact_external_id=f"cli_{key}",
                    status=ConversationStatus.open,
                    sentiment_score=score,
                    created_at=now - timedelta(hours=1),
                )
            )
        await session.flush()

        # Клиентское сообщение в каждом диалоге; в "nul" — без sentiment,
        # чтобы оно попало в pending. Для проанализированных проставляем
        # sentiment, чтобы /dashboard/sentiment видел analyzed.
        sentiments = {
            "neg": Sentiment.negative,
            "neu": Sentiment.neutral,
            "pos": Sentiment.positive,
            "nul": None,
        }
        for key in scores:
            session.add(
                Message(
                    id=f"ms_{key}",
                    conversation_id=f"cs_{key}",
                    sender_type=SenderType.client,
                    text=f"text {key}",
                    sent_at=now - timedelta(minutes=30),
                    sentiment=sentiments[key],
                    sentiment_at=(
                        now if sentiments[key] is not None else None
                    ),
                    sentiment_model="stub" if sentiments[key] else None,
                )
            )
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_conversation_list_includes_sentiment_score(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/conversations")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    by_id = {it["id"]: it for it in items}
    assert by_id["cs_neg"]["sentiment_score"] == pytest.approx(-0.8)
    assert by_id["cs_neu"]["sentiment_score"] == pytest.approx(0.0)
    assert by_id["cs_pos"]["sentiment_score"] == pytest.approx(0.7)
    assert by_id["cs_nul"]["sentiment_score"] is None


@pytest.mark.asyncio
async def test_conversation_filter_sentiment_negative(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/conversations?sentiment=negative")
    assert resp.status_code == 200, resp.text
    ids = [it["id"] for it in resp.json()]
    assert ids == ["cs_neg"]


@pytest.mark.asyncio
async def test_conversation_filter_sentiment_positive(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/conversations?sentiment=positive")
    assert resp.status_code == 200, resp.text
    ids = [it["id"] for it in resp.json()]
    assert ids == ["cs_pos"]


@pytest.mark.asyncio
async def test_conversation_filter_sentiment_neutral(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/conversations?sentiment=neutral")
    assert resp.status_code == 200, resp.text
    # neutral — попадает только cs_neu (0.0). cs_nul с None не должен попасть.
    ids = [it["id"] for it in resp.json()]
    assert ids == ["cs_neu"]


@pytest.mark.asyncio
async def test_overview_returns_sentiment_avg(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/overview?days=7")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # (-0.8 + 0.0 + 0.7) / 3 ≈ -0.0333
    assert data["sentiment_avg"] is not None
    assert data["sentiment_avg"] == pytest.approx((-0.8 + 0.0 + 0.7) / 3, rel=1e-3)
    # Прошлый период пуст
    assert data["sentiment_avg_prev"] is None
    # cs_nul — клиентское сообщение без sentiment
    assert data["sentiment_pending_messages"] == 1


@pytest.mark.asyncio
async def test_overview_sentiment_avg_null_when_no_data(client, auth_tenant_id):
    """Без проанализированных диалогов overview отдаёт None, не 0."""
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id="intg_empty",
                tenant_id=auth_tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Empty",
                domain="empty.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/dashboard/overview?days=7")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["sentiment_avg"] is None
    assert data["sentiment_avg_prev"] is None
    assert data["sentiment_pending_messages"] == 0


@pytest.mark.asyncio
async def test_top_negative_conversations(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/top-negative-conversations?limit=10")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    # По дефолту threshold=0.0 → только реально отрицательные. Нейтральный
    # cs_neu (0.0) и положительный cs_pos в выдачу не попадают.
    ids = [it["conversation_id"] for it in items]
    assert ids == ["cs_neg"]
    assert items[0]["sentiment_score"] == pytest.approx(-0.8)
    assert items[0]["message_count"] == 1


@pytest.mark.asyncio
async def test_top_negative_threshold_includes_neutral(client, auth_tenant_id):
    """При threshold=0.5 в выдачу попадают и нейтралы (score < 0.5)."""
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get(
        "/api/v1/dashboard/top-negative-conversations?threshold=0.5"
    )
    assert resp.status_code == 200, resp.text
    ids = [it["conversation_id"] for it in resp.json()["items"]]
    assert ids == ["cs_neg", "cs_neu"]


@pytest.mark.asyncio
async def test_top_negative_respects_limit(client, auth_tenant_id):
    await _seed_with_sentiment(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/top-negative-conversations?limit=1")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["conversation_id"] == "cs_neg"


@pytest.mark.asyncio
async def test_llm_status_unauthorized(monkeypatch):
    """Без bearer-токена /llm-status закрыт."""
    from httpx import ASGITransport, AsyncClient

    from app.db.session import Base, engine
    from app.main import app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        resp = await ac.get("/api/v1/system/llm-status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_llm_status_null_default(client):
    resp = await client.get("/api/v1/system/llm-status")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Дефолт в config.py — null-провайдер
    assert data == {"fast_available": False, "smart_available": False}


@pytest.mark.asyncio
async def test_llm_status_with_provider(client, monkeypatch):
    monkeypatch.setenv("LLM_FAST_PROVIDER", "groq")
    monkeypatch.setenv("LLM_FAST_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_SMART_PROVIDER", "claude")
    monkeypatch.delenv("LLM_SMART_API_KEY", raising=False)
    get_settings.cache_clear()
    try:
        resp = await client.get("/api/v1/system/llm-status")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["fast_available"] is True
        # smart без ключа — недоступен
        assert data["smart_available"] is False
    finally:
        get_settings.cache_clear()
