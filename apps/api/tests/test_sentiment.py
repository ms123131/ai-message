"""Тесты sentiment-анализа: парсер, классификатор, агрегат, API."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

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
from app.integrations.llm import reset_cache
from app.nlp.sentiment import (
    _parse_sentiment,
    analyze_messages_batch,
    classify,
    recompute_conversation_sentiment_score,
)


def test_parse_sentiment_canonical():
    assert _parse_sentiment("positive") == Sentiment.positive
    assert _parse_sentiment("negative") == Sentiment.negative
    assert _parse_sentiment("neutral") == Sentiment.neutral


def test_parse_sentiment_handles_quotes_and_caps():
    assert _parse_sentiment('"Positive"') == Sentiment.positive
    assert _parse_sentiment("NEGATIVE.") == Sentiment.negative
    assert _parse_sentiment("  Neutral!\n") == Sentiment.neutral


def test_parse_sentiment_first_word_wins():
    # Модель развернулась — берём первое слово
    assert _parse_sentiment("positive — клиент доволен") == Sentiment.positive
    assert _parse_sentiment("negative, because complaint") == Sentiment.negative


def test_parse_sentiment_garbage_returns_none():
    assert _parse_sentiment("") is None
    assert _parse_sentiment("???") is None
    assert _parse_sentiment("happy") is None  # не наш словарь


@pytest.fixture
async def with_null_llm(monkeypatch):
    """Гарантируем null-провайдера в fast-LLM (фабрика без сетевых вызовов)."""
    monkeypatch.setenv("LLM_FAST_PROVIDER", "null")
    monkeypatch.delenv("LLM_FAST_API_KEY", raising=False)
    get_settings.cache_clear()
    await reset_cache()
    yield
    get_settings.cache_clear()
    await reset_cache()


@pytest.fixture
async def with_stub_classify(monkeypatch):
    """Подмена classify() детерминированным маппером — без зависимости от LLM."""
    from app.nlp import sentiment as sentiment_mod

    async def _stub(text: str):
        t = (text or "").lower()
        if "плохо" in t or "ужас" in t or "bad" in t:
            return (Sentiment.negative, 1.0, "stub")
        if "спасибо" in t or "отлично" in t or "good" in t:
            return (Sentiment.positive, 1.0, "stub")
        return (Sentiment.neutral, 1.0, "stub")

    monkeypatch.setattr(sentiment_mod, "classify", _stub)
    return _stub


@pytest.mark.asyncio
async def test_classify_short_text_skips_llm(with_null_llm):
    """Короткие сообщения возвращают neutral без LLM-вызова."""
    result = await classify("ok")
    assert result == (Sentiment.neutral, 1.0, "trivial")


@pytest.mark.asyncio
async def test_classify_via_null_llm_returns_none(with_null_llm):
    """null-LLM отдаёт текст-заглушку, _parse_sentiment не найдёт label → None."""
    result = await classify("Какое-то длинное реальное сообщение клиента")
    # null-провайдер вернёт что-то типа "[null-llm] ..." — не наш словарь
    assert result is None


async def _seed_integration_with_messages(
    tenant_id: str,
    texts: list[tuple[str, SenderType]],
) -> tuple[str, str, list[str]]:
    """Возвращает (integration_id, conversation_id, [message_ids])."""
    integration_id = f"b24_{secrets.token_urlsafe(6).lower()}"
    conv_id = f"cnv_{secrets.token_urlsafe(6).lower()}"
    msg_ids: list[str] = []

    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="sentiment-test",
                domain="sentiment.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-1",
                channel=ConversationChannel.whatsapp,
                status=ConversationStatus.open,
            )
        )
        for i, (text, sender) in enumerate(texts):
            mid = f"msg_{secrets.token_urlsafe(6).lower()}"
            msg_ids.append(mid)
            session.add(
                Message(
                    id=mid,
                    conversation_id=conv_id,
                    sender_type=sender,
                    text=text,
                    sent_at=now - timedelta(minutes=len(texts) - i),
                )
            )
        await session.commit()
    return integration_id, conv_id, msg_ids


@pytest.mark.asyncio
async def test_analyze_messages_batch_writes_sentiment(
    client, auth_tenant_id, with_stub_classify
):
    _, _, msg_ids = await _seed_integration_with_messages(
        auth_tenant_id,
        [
            ("Спасибо, всё отлично!", SenderType.client),
            ("Это плохо, верните деньги", SenderType.client),
            ("Уточняю детали", SenderType.client),
        ],
    )

    async with AsyncSessionLocal() as session:
        processed = await analyze_messages_batch(session, msg_ids)
        await session.commit()

    assert processed == 3

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.id.in_(msg_ids))
            )
        ).scalars().all()
        by_text = {m.text: m for m in rows}
        assert by_text["Спасибо, всё отлично!"].sentiment == Sentiment.positive
        assert by_text["Это плохо, верните деньги"].sentiment == Sentiment.negative
        assert by_text["Уточняю детали"].sentiment == Sentiment.neutral
        # Метаданные заполнены
        for m in rows:
            assert m.sentiment_at is not None
            assert m.sentiment_model == "stub"
            assert m.sentiment_confidence == 1.0


@pytest.mark.asyncio
async def test_analyze_skips_already_processed(
    client, auth_tenant_id, with_stub_classify
):
    _, _, msg_ids = await _seed_integration_with_messages(
        auth_tenant_id,
        [("Спасибо!", SenderType.client)],
    )

    # Помечаем как уже обработанное
    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        msg.sentiment = Sentiment.neutral
        msg.sentiment_at = datetime.now(UTC)
        msg.sentiment_model = "previous-run"
        await session.commit()

    async with AsyncSessionLocal() as session:
        processed = await analyze_messages_batch(session, msg_ids)
        await session.commit()

    assert processed == 0  # повторно не классифицировали

    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        assert msg.sentiment_model == "previous-run"


@pytest.mark.asyncio
async def test_recompute_conversation_sentiment_score(
    client, auth_tenant_id, with_stub_classify
):
    _, conv_id, msg_ids = await _seed_integration_with_messages(
        auth_tenant_id,
        [
            ("Спасибо, всё отлично!", SenderType.client),  # +1
            ("Это плохо, ужас", SenderType.client),         # -1
            ("Здравствуйте, помогаю вам", SenderType.agent),  # игнор (агент)
        ],
    )

    async with AsyncSessionLocal() as session:
        await analyze_messages_batch(session, msg_ids)
        score = await recompute_conversation_sentiment_score(session, conv_id)
        await session.commit()

    # (1 + -1) / 2 = 0, среднее по клиентским
    assert score == 0.0

    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        assert conv.sentiment_score == 0.0


@pytest.mark.asyncio
async def test_dashboard_sentiment_endpoint(
    client, auth_tenant_id, with_stub_classify
):
    _, conv_id, msg_ids = await _seed_integration_with_messages(
        auth_tenant_id,
        [
            ("Отлично, спасибо!", SenderType.client),
            ("Плохо, всё плохо", SenderType.client),
            ("Сейчас помогу", SenderType.agent),  # не клиент — не в счёт
        ],
    )

    async with AsyncSessionLocal() as session:
        await analyze_messages_batch(session, msg_ids)
        await recompute_conversation_sentiment_score(session, conv_id)
        await session.commit()

    resp = await client.get("/api/v1/dashboard/sentiment?days=30")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_messages"] == 2  # только клиентские
    assert body["analyzed_messages"] == 2
    assert body["pending_messages"] == 0

    by_sentiment = {b["sentiment"]: b for b in body["buckets"]}
    assert by_sentiment["positive"]["count"] == 1
    assert by_sentiment["negative"]["count"] == 1
    assert by_sentiment["neutral"]["count"] == 0
    assert body["avg_score"] == 0.0


@pytest.mark.asyncio
async def test_analyze_sentiment_endpoint_enqueues_job(
    client, auth_tenant_id, _stub_arq_pool
):
    integration_id, _, _ = await _seed_integration_with_messages(
        auth_tenant_id,
        [("текст", SenderType.client)],
    )

    resp = await client.post(
        f"/api/v1/integrations/{integration_id}/analyze-sentiment?batch_size=50"
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "accepted"

    # Проверяем, что задача попала в arq-пул (через стаб из conftest)
    names = [name for name, _, _ in _stub_arq_pool.enqueued]
    assert "analyze_sentiment_for_integration" in names
