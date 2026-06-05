"""Тесты cursor-пагинации для /api/v1/conversations + поддержки
денормализованных last_message_at / last_message_preview."""

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


async def _seed_conversations(tenant_id: str, n: int) -> list[str]:
    """Создаёт n диалогов с разными last_message_at для проверки сортировки."""
    integration_id = f"intg_cur_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    conv_ids: list[str] = []
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Cur",
                domain="cur.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        for i in range(n):
            cid = f"cvr_{i:03d}_{secrets.token_urlsafe(3)}"
            conv_ids.append(cid)
            last_at = now - timedelta(minutes=i)
            session.add(
                Conversation(
                    id=cid,
                    integration_id=integration_id,
                    external_id=f"ext-{i}",
                    channel=ConversationChannel.whatsapp,
                    status=ConversationStatus.open,
                    last_message_at=last_at,
                    last_message_preview=f"preview {i}",
                )
            )
            session.add(
                Message(
                    id=f"mid_{cid}",
                    conversation_id=cid,
                    sender_type=SenderType.client,
                    text=f"hello {i}",
                    sent_at=last_at,
                )
            )
        await session.commit()
    return conv_ids


@pytest.mark.asyncio
async def test_list_returns_items_and_next_cursor(client, auth_tenant_id):
    conv_ids = await _seed_conversations(auth_tenant_id, n=5)
    resp = await client.get("/api/v1/conversations?limit=3")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"items", "next_cursor"}
    assert len(body["items"]) == 3
    # Сортировка по last_message_at DESC: первые 3 — самые свежие (id 000, 001, 002)
    assert [it["id"] for it in body["items"]] == conv_ids[:3]
    assert body["next_cursor"] is not None


@pytest.mark.asyncio
async def test_list_paginates_via_cursor(client, auth_tenant_id):
    conv_ids = await _seed_conversations(auth_tenant_id, n=5)

    page1 = (await client.get("/api/v1/conversations?limit=2")).json()
    assert [it["id"] for it in page1["items"]] == conv_ids[:2]
    assert page1["next_cursor"]

    page2 = (
        await client.get(
            f"/api/v1/conversations?limit=2&cursor={page1['next_cursor']}"
        )
    ).json()
    assert [it["id"] for it in page2["items"]] == conv_ids[2:4]
    assert page2["next_cursor"]

    page3 = (
        await client.get(
            f"/api/v1/conversations?limit=2&cursor={page2['next_cursor']}"
        )
    ).json()
    # Последний диалог + флаг конца
    assert [it["id"] for it in page3["items"]] == conv_ids[4:5]
    assert page3["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_exposes_denormalized_preview(client, auth_tenant_id):
    await _seed_conversations(auth_tenant_id, n=1)
    resp = await client.get("/api/v1/conversations?limit=10")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    # last_message_preview берётся напрямую из колонки, без второго JOIN
    assert item["last_message_preview"] == "preview 0"
    assert item["last_message_at"] is not None
    assert item["message_count"] == 1


@pytest.mark.asyncio
async def test_list_invalid_cursor_returns_empty_or_400(client, auth_tenant_id):
    """Битый cursor не должен приводить к 500. Поведение текущей реализации:
    игнорируем cursor (как будто его нет) — это безопасно, фронт получит
    первую страницу заново."""
    await _seed_conversations(auth_tenant_id, n=2)
    resp = await client.get("/api/v1/conversations?cursor=garbage!!!")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


@pytest.mark.asyncio
async def test_cursor_helper_roundtrip():
    from app.api.v1._cursor import decode_cursor, encode_cursor

    now = datetime.now(UTC)
    token = encode_cursor(now, "abc")
    decoded = decode_cursor(token)
    assert decoded is not None
    last_at, id_ = decoded
    assert id_ == "abc"
    assert last_at == now

    # Версия отсутствует / битая base64
    assert decode_cursor("not-base64!!") is None
    assert decode_cursor("") is None
    assert decode_cursor(None) is None
