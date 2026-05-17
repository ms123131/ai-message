"""Тесты /api/v1/dashboard/stats."""

from __future__ import annotations

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


async def _seed() -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_dash",
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="Dash",
            domain="portal.bitrix24.ru",
            status=IntegrationStatus.connected,
        )
        session.add(integration)
        await session.flush()

        now = datetime.now(UTC)
        conv1 = Conversation(
            id="c1",
            integration_id=integration.id,
            external_id="ext1",
            channel=ConversationChannel.telegram,
            contact_name="Ivan",
            status=ConversationStatus.open,
        )
        conv2 = Conversation(
            id="c2",
            integration_id=integration.id,
            external_id="ext2",
            channel=ConversationChannel.whatsapp,
            contact_name="Maria",
            status=ConversationStatus.closed,
        )
        session.add_all([conv1, conv2])
        await session.flush()

        msgs = [
            Message(
                id=f"m{i}",
                conversation_id="c1",
                sender_type=SenderType.client,
                text=f"hi {i}",
                sent_at=now - timedelta(days=i % 3),
            )
            for i in range(5)
        ] + [
            Message(
                id="m_wa",
                conversation_id="c2",
                sender_type=SenderType.agent,
                text="hello",
                sent_at=now - timedelta(days=1),
            )
        ]
        session.add_all(msgs)
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_stats_returns_aggregates(client):
    await _seed()
    resp = await client.get("/api/v1/dashboard/stats?days=14")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_conversations"] == 2
    assert data["open_conversations"] == 1
    assert data["total_messages"] == 6
    assert len(data["volume_by_day"]) == 14
    channels = {c["channel"]: c for c in data["by_channel"]}
    assert channels["telegram"]["messages"] == 5
    assert channels["whatsapp"]["messages"] == 1


@pytest.mark.asyncio
async def test_stats_filter_by_integration(client):
    integration_id = await _seed()
    resp = await client.get(
        f"/api/v1/dashboard/stats?integration_id={integration_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_conversations"] == 2

    resp_empty = await client.get(
        "/api/v1/dashboard/stats?integration_id=nonexistent"
    )
    assert resp_empty.status_code == 200
    assert resp_empty.json()["total_conversations"] == 0


@pytest.mark.asyncio
async def test_stats_empty(client):
    resp = await client.get("/api/v1/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_conversations"] == 0
    assert data["total_messages"] == 0
    assert data["by_channel"] == []
    assert len(data["volume_by_day"]) == 14
    assert all(p["count"] == 0 for p in data["volume_by_day"])
