"""Тесты приёма событий Bitrix24 через /api/v1/webhooks/bitrix24."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models import (
    Conversation,
    ConversationChannel,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
    Message,
    SenderType,
)
from app.db.session import AsyncSessionLocal


def _form_payload(
    *,
    event: str = "ONOPENLINEMESSAGEADD",
    chat_id: str = "12345",
    message: str = "Привет, помогите с заказом",
    message_id: str = "msg_ext_1",
    # message.user_id во внутренней B24-нумерации; для клиента совпадает с connector.user_id
    message_user_id: str = "1985",
    connector_user_id: str = "1985",
    connector: str = "telegram",
    system: str = "N",
    member_id: str = "member-portal-1",
    domain: str = "portal.bitrix24.ru",
    ts: str = "1717000000",
) -> dict[str, str]:
    return {
        "event": event,
        "eventId": "1",
        "ts": ts,
        "data[DATA][0][connector][connector_id]": connector,
        "data[DATA][0][connector][line_id]": "128",
        "data[DATA][0][connector][chat_id]": "tg_external_42",
        "data[DATA][0][connector][user_id]": connector_user_id,
        "data[DATA][0][chat][id]": chat_id,
        "data[DATA][0][message][id]": message_id,
        "data[DATA][0][message][date]": "",
        "data[DATA][0][message][text]": message,
        "data[DATA][0][message][system]": system,
        "data[DATA][0][message][user_id]": message_user_id,
        "auth[domain]": domain,
        "auth[member_id]": member_id,
        "auth[application_token]": "app-token",
    }


async def _make_integration(
    member_id: str = "member-portal-1",
    tenant_id: str | None = None,
) -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_portal_1",
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="Test",
            domain="portal.bitrix24.ru",
            status=IntegrationStatus.connected,
            member_id=member_id,
        )
        session.add(integration)
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_webhook_creates_conversation_and_message(client):
    await _make_integration()
    resp = await client.post(
        "/api/v1/webhooks/bitrix24",
        data=_form_payload(),
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["result"] == "ingested"

    async with AsyncSessionLocal() as session:
        convs = (await session.execute(select(Conversation))).scalars().all()
        assert len(convs) == 1
        conv = convs[0]
        assert conv.channel == ConversationChannel.telegram
        assert conv.external_id == "12345"
        assert conv.integration_id == "intg_portal_1"

        msgs = (await session.execute(select(Message))).scalars().all()
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg.text == "Привет, помогите с заказом"
        assert msg.sender_type == SenderType.client
        assert msg.external_id == "msg_ext_1"


@pytest.mark.asyncio
async def test_webhook_dedupes_repeated_event(client):
    await _make_integration()
    payload = _form_payload()
    first = await client.post("/api/v1/webhooks/bitrix24", data=payload)
    assert first.json()["result"] == "ingested"

    second = await client.post("/api/v1/webhooks/bitrix24", data=payload)
    assert second.status_code == 202
    assert second.json()["result"] == "duplicate"

    async with AsyncSessionLocal() as session:
        assert len((await session.execute(select(Message))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_webhook_appends_to_existing_conversation(client):
    await _make_integration()
    await client.post("/api/v1/webhooks/bitrix24", data=_form_payload(message_id="m1"))
    await client.post(
        "/api/v1/webhooks/bitrix24",
        data=_form_payload(
            message_id="m2",
            message="а вот и второе сообщение",
            # message.user_id != connector.user_id → оператор
            message_user_id="100",
        ),
    )
    async with AsyncSessionLocal() as session:
        convs = (await session.execute(select(Conversation))).scalars().all()
        assert len(convs) == 1
        msgs = (await session.execute(select(Message))).scalars().all()
        assert len(msgs) == 2
        senders = {m.sender_type for m in msgs}
        assert senders == {SenderType.client, SenderType.agent}


@pytest.mark.asyncio
async def test_webhook_returns_no_integration_when_unknown_portal(client):
    resp = await client.post(
        "/api/v1/webhooks/bitrix24",
        data=_form_payload(member_id="who-knows", domain="nope.bitrix24.ru"),
    )
    assert resp.status_code == 202
    assert resp.json()["result"] == "no_integration"


@pytest.mark.asyncio
async def test_webhook_ignores_unsupported_event(client):
    await _make_integration()
    resp = await client.post(
        "/api/v1/webhooks/bitrix24",
        data={
            "event": "ONCRMDEALUPDATE",
            "auth[domain]": "portal.bitrix24.ru",
            "auth[member_id]": "member-portal-1",
        },
    )
    assert resp.status_code == 202
    assert resp.json()["result"] == "unsupported"


@pytest.mark.asyncio
async def test_read_api_lists_conversations_and_messages(client, auth_tenant_id):
    await _make_integration(tenant_id=auth_tenant_id)
    await client.post("/api/v1/webhooks/bitrix24", data=_form_payload(message_id="m1"))
    await client.post(
        "/api/v1/webhooks/bitrix24",
        data=_form_payload(message_id="m2", message="второе"),
    )

    list_resp = await client.get("/api/v1/conversations")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["channel"] == "telegram"
    assert item["message_count"] == 2
    assert item["last_message_preview"]

    conv_id = item["id"]
    msgs_resp = await client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert msgs_resp.status_code == 200
    msgs = msgs_resp.json()
    assert [m["external_id"] for m in msgs] == ["m1", "m2"]
