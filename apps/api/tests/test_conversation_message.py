"""Тесты для моделей Conversation и Message."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

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
from app.db.session import AsyncSessionLocal, Base, engine


@pytest.fixture(autouse=True)
async def _setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _make_integration(integration_id: str = "intg_1") -> Integration:
    return Integration(
        id=integration_id,
        kind=IntegrationKind.bitrix24,
        mode=IntegrationMode.webhook,
        label="Test",
        domain="test.bitrix24.ru",
        status=IntegrationStatus.connected,
        webhook_url="https://test.bitrix24.ru/rest/1/abc",
    )


def _make_conversation(integration_id: str, conv_id: str = "conv_1", external: str = "ext_1"):
    return Conversation(
        id=conv_id,
        integration_id=integration_id,
        external_id=external,
        channel=ConversationChannel.telegram,
        contact_name="Иван",
        status=ConversationStatus.open,
    )


def _make_message(conv_id: str, msg_id: str, *, external: str | None = None, text: str = "hi"):
    return Message(
        id=msg_id,
        conversation_id=conv_id,
        external_id=external,
        sender_type=SenderType.client,
        text=text,
        sent_at=datetime.now(UTC),
    )


async def test_create_conversation_with_messages():
    async with AsyncSessionLocal() as session:
        integration = _make_integration()
        session.add(integration)
        await session.flush()

        conv = _make_conversation(integration.id)
        session.add(conv)
        await session.flush()

        m1 = _make_message(conv.id, "m1", external="ext_m1", text="привет")
        m2 = _make_message(conv.id, "m2", external="ext_m2", text="как дела")
        m2.sender_type = SenderType.agent
        m2.sent_at = m1.sent_at + timedelta(seconds=30)
        session.add_all([m1, m2])
        await session.commit()

        loaded = await session.get(Conversation, conv.id)
        assert loaded is not None
        await session.refresh(loaded, attribute_names=["messages"])
        assert len(loaded.messages) == 2
        assert [m.id for m in loaded.messages] == ["m1", "m2"]  # order_by sent_at


async def test_conversation_unique_per_integration():
    async with AsyncSessionLocal() as session:
        integration = _make_integration()
        session.add(integration)
        session.add(_make_conversation(integration.id, "c1", "EXT-42"))
        await session.commit()

    async with AsyncSessionLocal() as session:
        session.add(_make_conversation("intg_1", "c2", "EXT-42"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_message_external_id_unique_per_conversation():
    async with AsyncSessionLocal() as session:
        integration = _make_integration()
        conv = _make_conversation(integration.id)
        session.add_all([integration, conv])
        await session.flush()
        session.add(_make_message(conv.id, "m1", external="dup"))
        session.add(_make_message(conv.id, "m2", external="dup"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_message_external_id_null_allowed_multiple_times():
    """Partial unique index не должен мешать сообщениям без external_id."""
    async with AsyncSessionLocal() as session:
        integration = _make_integration()
        conv = _make_conversation(integration.id)
        session.add_all([integration, conv])
        await session.flush()
        session.add(_make_message(conv.id, "m1", external=None))
        session.add(_make_message(conv.id, "m2", external=None))
        await session.commit()
        result = await session.execute(select(Message))
        assert len(result.scalars().all()) == 2


async def test_cascade_delete_integration_removes_conversations_and_messages():
    async with AsyncSessionLocal() as session:
        integration = _make_integration()
        conv = _make_conversation(integration.id)
        session.add_all([integration, conv])
        await session.flush()
        session.add(_make_message(conv.id, "m1", external="ext_m1"))
        await session.commit()

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, "intg_1")
        assert integration is not None
        await session.delete(integration)
        await session.commit()

    async with AsyncSessionLocal() as session:
        assert (await session.execute(select(Conversation))).scalars().first() is None
        assert (await session.execute(select(Message))).scalars().first() is None


async def test_attachments_roundtrip_json():
    async with AsyncSessionLocal() as session:
        integration = _make_integration()
        conv = _make_conversation(integration.id)
        session.add_all([integration, conv])
        await session.flush()
        msg = _make_message(conv.id, "m1", external="ext_m1")
        msg.attachments = [
            {"url": "https://example/file.pdf", "name": "doc.pdf", "size": 1024},
        ]
        session.add(msg)
        await session.commit()

    async with AsyncSessionLocal() as session:
        loaded = await session.get(Message, "m1")
        assert loaded is not None
        assert loaded.attachments == [
            {"url": "https://example/file.pdf", "name": "doc.pdf", "size": 1024},
        ]
