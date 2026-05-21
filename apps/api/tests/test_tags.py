"""Тесты авто-тегирования (фаза 6.2)."""

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
)
from app.db.session import AsyncSessionLocal
from app.integrations.llm.base import LLMResponse
from app.nlp.tags import (
    _parse_tags,
    analyze_messages_tags_batch,
    get_vocabulary,
    recompute_conversation_tags,
)

# ---------------------------------------------------------------------------
# _parse_tags — unit
# ---------------------------------------------------------------------------


def test_parse_tags_canonical():
    vocab = ["оплата", "доставка", "возврат"]
    assert _parse_tags("оплата, доставка", vocab) == ["оплата", "доставка"]


def test_parse_tags_handles_spaces_as_underscores():
    vocab = ["статус_заказа", "техподдержка"]
    # Модель может вернуть с пробелами вместо подчёркиваний
    assert _parse_tags("статус заказа, техподдержка", vocab) == [
        "статус_заказа",
        "техподдержка",
    ]


def test_parse_tags_filters_unknown():
    vocab = ["оплата", "доставка"]
    assert _parse_tags("оплата, выдуманная_тема", vocab) == ["оплата"]


def test_parse_tags_caps_at_three():
    vocab = ["a", "b", "c", "d", "e"]
    assert _parse_tags("a, b, c, d, e", vocab) == ["a", "b", "c"]


def test_parse_tags_dedup():
    vocab = ["оплата"]
    assert _parse_tags("оплата, оплата", vocab) == ["оплата"]


def test_parse_tags_none_token():
    vocab = ["оплата"]
    assert _parse_tags("none", vocab) == []
    assert _parse_tags("—", vocab) == []
    assert _parse_tags("", vocab) == []


def test_parse_tags_tolerant_to_quotes_and_pipes():
    vocab = ["оплата", "доставка"]
    assert _parse_tags('"оплата"; доставка.', vocab) == ["оплата", "доставка"]


# ---------------------------------------------------------------------------
# get_vocabulary — конфиг
# ---------------------------------------------------------------------------


def test_get_vocabulary_default_has_essentials():
    vocab = get_vocabulary()
    assert "оплата" in vocab
    assert "доставка" in vocab


def test_get_vocabulary_respects_env(monkeypatch):
    monkeypatch.setenv("TAGS_VOCABULARY", "только_одна_тема, и_вторая")
    get_settings.cache_clear()
    try:
        assert get_vocabulary() == ["только_одна_тема", "и_вторая"]
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Stub fast-LLM и батч-обработка
# ---------------------------------------------------------------------------


class _FakeLLM:
    name = "fake-fast"
    default_model = "fake-tiny"

    def __init__(self, responses: dict[str, str]):
        """responses: text → ответ модели (строка для парсера)."""
        self.responses = responses
        self.calls = 0

    async def chat(self, messages, **kwargs):  # noqa: ANN001
        # Возвращаем ответ, соответствующий тексту user-сообщения.
        self.calls += 1
        user_msg = next((m for m in messages if m.role == "user"), None)
        text = user_msg.content if user_msg else ""
        out = self.responses.get(text, "none")
        return LLMResponse(content=out, model=self.default_model)

    async def aclose(self):
        pass


@pytest.fixture
async def with_fake_fast(monkeypatch):
    from app.integrations import llm as llm_pkg
    from app.integrations.llm import factory
    from app.nlp import tags as tags_mod

    fake = _FakeLLM(
        {
            "Не пришёл заказ, что делать?": "доставка, статус заказа",
            "Оплатил, но не списались деньги": "оплата",
            "Хочу вернуть товар": "возврат, жалоба",
            "просто привет": "none",
        }
    )

    def _get(kind="fast"):
        return fake

    monkeypatch.setattr(factory, "get_llm", _get)
    monkeypatch.setattr(llm_pkg, "get_llm", _get)
    monkeypatch.setattr(tags_mod, "get_llm", _get)
    return fake


async def _seed_messages(
    tenant_id: str,
    texts: list[tuple[str, SenderType]],
    return_conv: bool = False,
):
    """Возвращает (integration_id, [message_ids]) либо
    (integration_id, conv_id, [message_ids]) при return_conv=True."""
    integration_id = f"intg_tags_{secrets.token_urlsafe(3)}"
    conv_id = f"cnv_tags_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    msg_ids: list[str] = []
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Tags",
                domain="tags.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-t",
                channel=ConversationChannel.whatsapp,
                status=ConversationStatus.open,
            )
        )
        for i, (text, sender) in enumerate(texts):
            mid = f"mt_{secrets.token_urlsafe(3)}"
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
    if return_conv:
        return integration_id, conv_id, msg_ids
    return integration_id, msg_ids


@pytest.mark.asyncio
async def test_analyze_messages_tags_writes(client, auth_tenant_id, with_fake_fast):
    _, msg_ids = await _seed_messages(
        auth_tenant_id,
        [
            ("Не пришёл заказ, что делать?", SenderType.client),
            ("Оплатил, но не списались деньги", SenderType.client),
            ("просто привет", SenderType.client),
        ],
    )
    async with AsyncSessionLocal() as session:
        n = await analyze_messages_tags_batch(session, msg_ids)
        await session.commit()
    assert n == 3
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(Message).where(Message.id.in_(msg_ids)))
        ).scalars().all()
        by_text = {m.text: m for m in rows}
        assert by_text["Не пришёл заказ, что делать?"].tags == [
            "доставка",
            "статус_заказа",
        ]
        assert by_text["Оплатил, но не списались деньги"].tags == ["оплата"]
        # «none» из словаря — пустой список, но запись есть (tags_at заполнен).
        attempt = by_text["просто привет"]
        assert attempt.tags == []
        assert attempt.tags_at is not None


@pytest.mark.asyncio
async def test_analyze_tags_skips_already_tagged(
    client, auth_tenant_id, with_fake_fast
):
    _, msg_ids = await _seed_messages(
        auth_tenant_id,
        [("Не пришёл заказ, что делать?", SenderType.client)],
    )
    # Помечаем уже обработанным
    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        msg.tags = ["доставка"]
        msg.tags_at = datetime.now(UTC)
        msg.tags_model = "previous"
        await session.commit()

    async with AsyncSessionLocal() as session:
        n = await analyze_messages_tags_batch(session, msg_ids)
        await session.commit()

    assert n == 0
    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        assert msg.tags_model == "previous"  # не переписали


@pytest.mark.asyncio
async def test_analyze_tags_endpoint_enqueues(client, auth_tenant_id, _stub_arq_pool):
    integration_id, _ = await _seed_messages(
        auth_tenant_id, [("текст", SenderType.client)]
    )
    resp = await client.post(
        f"/api/v1/integrations/{integration_id}/analyze-tags?batch_size=50"
    )
    assert resp.status_code == 202, resp.text
    names = [name for name, _, _ in _stub_arq_pool.enqueued]
    assert "analyze_tags_for_integration" in names


@pytest.mark.asyncio
async def test_dashboard_tags_aggregates(client, auth_tenant_id, with_fake_fast):
    _, msg_ids = await _seed_messages(
        auth_tenant_id,
        [
            ("Не пришёл заказ, что делать?", SenderType.client),
            ("Оплатил, но не списались деньги", SenderType.client),
            ("Хочу вернуть товар", SenderType.client),
            ("просто привет", SenderType.client),
        ],
    )
    async with AsyncSessionLocal() as session:
        await analyze_messages_tags_batch(session, msg_ids)
        await session.commit()

    resp = await client.get("/api/v1/dashboard/tags?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_messages"] == 4
    assert body["analyzed_messages"] == 4
    by_tag = {b["tag"]: b for b in body["buckets"]}
    # «доставка», «статус_заказа», «оплата», «возврат», «жалоба» должны быть
    assert by_tag["доставка"]["count"] == 1
    assert by_tag["оплата"]["count"] == 1
    assert by_tag["возврат"]["count"] == 1
    assert by_tag["жалоба"]["count"] == 1
    # share по analyzed (4)
    assert by_tag["доставка"]["share"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# recompute_conversation_tags — денормализация на уровне диалога
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recompute_conversation_tags_unions_client_messages(
    client, auth_tenant_id, with_fake_fast
):
    _, conv_id, msg_ids = await _seed_messages(
        auth_tenant_id,
        [
            ("Не пришёл заказ, что делать?", SenderType.client),
            ("Хочу вернуть товар", SenderType.client),
            # Сообщение оператора не должно влиять, даже если есть теги
            ("Оплатил, но не списались деньги", SenderType.agent),
        ],
        return_conv=True,
    )
    async with AsyncSessionLocal() as session:
        await analyze_messages_tags_batch(session, msg_ids)
        result = await recompute_conversation_tags(session, conv_id)
        await session.commit()

    # Только клиентские сообщения: доставка, статус_заказа, возврат, жалоба
    assert result == sorted(["доставка", "статус_заказа", "возврат", "жалоба"])

    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        assert conv.tags == sorted([
            "доставка",
            "статус_заказа",
            "возврат",
            "жалоба",
        ])


@pytest.mark.asyncio
async def test_recompute_conversation_tags_returns_none_when_unanalyzed(
    client, auth_tenant_id
):
    _, conv_id, _ = await _seed_messages(
        auth_tenant_id,
        [("текст без анализа", SenderType.client)],
        return_conv=True,
    )
    async with AsyncSessionLocal() as session:
        result = await recompute_conversation_tags(session, conv_id)
        await session.commit()
    assert result is None
    async with AsyncSessionLocal() as session:
        conv = await session.get(Conversation, conv_id)
        assert conv.tags is None


@pytest.mark.asyncio
async def test_conversation_list_exposes_tags(
    client, auth_tenant_id, with_fake_fast
):
    integration_id, conv_id, msg_ids = await _seed_messages(
        auth_tenant_id,
        [("Не пришёл заказ, что делать?", SenderType.client)],
        return_conv=True,
    )
    async with AsyncSessionLocal() as session:
        await analyze_messages_tags_batch(session, msg_ids)
        await recompute_conversation_tags(session, conv_id)
        await session.commit()

    resp = await client.get(
        f"/api/v1/conversations?integration_id={integration_id}"
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert items
    target = next(i for i in items if i["id"] == conv_id)
    assert sorted(target["tags"]) == sorted(["доставка", "статус_заказа"])
