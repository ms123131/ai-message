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


async def _seed(tenant_id: str | None = None) -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_dash",
            tenant_id=tenant_id,
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
async def test_stats_returns_aggregates(client, auth_tenant_id):
    await _seed(tenant_id=auth_tenant_id)
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
async def test_stats_filter_by_integration(client, auth_tenant_id):
    integration_id = await _seed(tenant_id=auth_tenant_id)
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


async def _seed_with_operator(tenant_id: str) -> str:
    """Дополнительный сидинг: 1 интеграция, 2 диалога с оператором, FRT и сообщения."""
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_mng",
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="Mng",
            domain="m.bitrix24.ru",
            status=IntegrationStatus.connected,
        )
        session.add(integration)
        await session.flush()

        from app.db.models import PortalUser

        session.add(
            PortalUser(
                id="pu_99",
                integration_id=integration.id,
                external_id="99",
                full_name="Иван Оператор",
                email="ivan@example.com",
                work_position="Senior support",
                avatar_url=None,
                is_active=True,
            )
        )

        now = datetime.now(UTC)
        c1 = Conversation(
            id="cm1",
            integration_id=integration.id,
            external_id="ext_m1",
            channel=ConversationChannel.telegram,
            contact_name="Alex",
            contact_external_id="cli_1",
            status=ConversationStatus.open,
            assigned_user_id="99",
            line_id="3",
            first_message_at=now - timedelta(hours=2),
            first_agent_reply_at=now - timedelta(hours=2) + timedelta(seconds=60),
            response_time_sec=60,
            created_at=now - timedelta(hours=2),
        )
        c2 = Conversation(
            id="cm2",
            integration_id=integration.id,
            external_id="ext_m2",
            channel=ConversationChannel.telegram,
            contact_name="Bob",
            contact_external_id="cli_2",
            status=ConversationStatus.closed,
            assigned_user_id="99",
            line_id="3",
            first_message_at=now - timedelta(hours=5),
            first_agent_reply_at=now - timedelta(hours=5) + timedelta(seconds=180),
            response_time_sec=180,
            closed_at=now - timedelta(hours=4),
            created_at=now - timedelta(hours=5),
        )
        session.add_all([c1, c2])
        await session.flush()
        session.add_all(
            [
                Message(
                    id="mm1",
                    conversation_id="cm1",
                    sender_type=SenderType.client,
                    text="hi",
                    sent_at=now - timedelta(hours=2),
                    sender_external_id="cli_1",
                ),
                Message(
                    id="mm2",
                    conversation_id="cm1",
                    sender_type=SenderType.agent,
                    sender_external_id="99",
                    text="hello",
                    sent_at=now - timedelta(hours=2) + timedelta(seconds=60),
                ),
                Message(
                    id="mm3",
                    conversation_id="cm2",
                    sender_type=SenderType.client,
                    text="problem",
                    sent_at=now - timedelta(hours=5),
                    sender_external_id="cli_2",
                ),
                Message(
                    id="mm4",
                    conversation_id="cm2",
                    sender_type=SenderType.agent,
                    sender_external_id="99",
                    text="solved",
                    sent_at=now - timedelta(hours=5) + timedelta(seconds=180),
                ),
            ]
        )
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_overview_returns_kpis(client, auth_tenant_id):
    await _seed_with_operator(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/overview?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversations"]["value"] == 2
    assert data["messages"]["value"] == 4
    assert data["open_now"] == 1
    assert data["frt_median_sec"]["value"] > 0
    assert data["unique_contacts"]["value"] == 2


@pytest.mark.asyncio
async def test_by_manager_lists_operators(client, auth_tenant_id):
    await _seed_with_operator(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/by-manager?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["operator_id"] == "99"
    assert row["full_name"] == "Иван Оператор"
    assert row["conversations"] == 2
    assert row["open_conversations"] == 1
    assert row["messages_sent"] == 2


@pytest.mark.asyncio
async def test_top_contacts(client, auth_tenant_id):
    await _seed_with_operator(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/top-contacts?days=7&limit=10")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert {it["contact_external_id"] for it in items} == {"cli_1", "cli_2"}


@pytest.mark.asyncio
async def test_portal_users_filters_by_tenant(client, auth_tenant_id):
    await _seed_with_operator(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/portal-users")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["full_name"] == "Иван Оператор"


@pytest.mark.asyncio
async def test_timeline_returns_points(client, auth_tenant_id):
    await _seed_with_operator(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/timeline?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["range_days"] == 7
    assert len(data["points"]) == 7
    total_messages = sum(p["messages"] for p in data["points"])
    assert total_messages == 4


@pytest.mark.asyncio
async def test_by_channel(client, auth_tenant_id):
    await _seed_with_operator(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/by-channel?days=7")
    assert resp.status_code == 200
    slices = resp.json()["slices"]
    assert len(slices) == 1
    assert slices[0]["channel"] == "telegram"
    assert slices[0]["conversations"] == 2
    assert slices[0]["messages"] == 4


@pytest.mark.asyncio
async def test_sla_breaches(client, auth_tenant_id):
    """Создаём открытый диалог с клиентским сообщением 30 минут назад → должно быть нарушение."""
    integration_id = await _seed_with_operator(auth_tenant_id)
    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        c = Conversation(
            id="cm_sla",
            integration_id=integration_id,
            external_id="ext_sla",
            channel=ConversationChannel.whatsapp,
            contact_name="Waiting",
            contact_external_id="cli_sla",
            status=ConversationStatus.open,
            assigned_user_id="99",
        )
        session.add(c)
        await session.flush()
        session.add(
            Message(
                id="m_sla",
                conversation_id="cm_sla",
                sender_type=SenderType.client,
                text="anyone there?",
                sent_at=now - timedelta(minutes=30),
                sender_external_id="cli_sla",
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/dashboard/sla-breaches?threshold_minutes=15")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["conversation_id"] == "cm_sla" for i in items)
    breach = next(i for i in items if i["conversation_id"] == "cm_sla")
    assert breach["operator_name"] == "Иван Оператор"
    assert breach["minutes_waiting"] >= 15


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
