"""Тесты фильтров /api/v1/conversations: tags[] + tag_mode + q (FTS).

Фаза 7 UX-итерация B (батч 2). На SQLite FTS заменён на ILIKE — это
покрывает большинство dev-кейсов, продовое поведение остаётся как было
(websearch_to_tsquery на russian-конфиге).
"""

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


async def _seed(
    tenant_id: str,
    rows: list[tuple[str, list[str] | None, str]],
) -> dict[str, str]:
    """rows = [(suffix, tags, message_text), ...]. Возвращает {suffix: conv_id}."""
    integration_id = f"intg_flt_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    mapping: dict[str, str] = {}
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Flt",
                domain="flt.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        for i, (suffix, tags, msg_text) in enumerate(rows):
            cid = f"cvf_{suffix}_{secrets.token_urlsafe(3)}"
            mapping[suffix] = cid
            last_at = now - timedelta(minutes=i)
            session.add(
                Conversation(
                    id=cid,
                    integration_id=integration_id,
                    external_id=f"ext-{suffix}",
                    channel=ConversationChannel.whatsapp,
                    status=ConversationStatus.open,
                    last_message_at=last_at,
                    last_message_preview=msg_text[:80],
                    tags=tags,
                )
            )
            session.add(
                Message(
                    id=f"mid_{cid}",
                    conversation_id=cid,
                    sender_type=SenderType.client,
                    text=msg_text,
                    sent_at=last_at,
                )
            )
        await session.commit()
    return mapping


@pytest.mark.asyncio
async def test_filter_by_single_tag(client, auth_tenant_id):
    ids = await _seed(
        auth_tenant_id,
        [
            ("pay", ["оплата"], "оплата прошла"),
            ("delivery", ["доставка"], "когда привезут"),
            ("none", None, "просто привет"),
        ],
    )
    resp = await client.get("/api/v1/conversations?tags=оплата")
    assert resp.status_code == 200, resp.text
    got = [it["id"] for it in resp.json()["items"]]
    assert ids["pay"] in got
    assert ids["delivery"] not in got
    assert ids["none"] not in got


@pytest.mark.asyncio
async def test_filter_by_tags_any_mode(client, auth_tenant_id):
    ids = await _seed(
        auth_tenant_id,
        [
            ("pay", ["оплата"], "оплата"),
            ("dlv", ["доставка"], "доставка"),
            ("other", ["жалоба"], "жалоба"),
        ],
    )
    resp = await client.get(
        "/api/v1/conversations?tags=оплата&tags=доставка&tag_mode=any"
    )
    assert resp.status_code == 200
    got = {it["id"] for it in resp.json()["items"]}
    assert ids["pay"] in got
    assert ids["dlv"] in got
    assert ids["other"] not in got


@pytest.mark.asyncio
async def test_filter_by_tags_all_mode(client, auth_tenant_id):
    ids = await _seed(
        auth_tenant_id,
        [
            ("both", ["оплата", "доставка"], "оплатил, когда привезёте"),
            ("pay_only", ["оплата"], "только оплата"),
            ("dlv_only", ["доставка"], "только доставка"),
        ],
    )
    resp = await client.get(
        "/api/v1/conversations?tags=оплата&tags=доставка&tag_mode=all"
    )
    assert resp.status_code == 200
    got = {it["id"] for it in resp.json()["items"]}
    assert ids["both"] in got
    assert ids["pay_only"] not in got
    assert ids["dlv_only"] not in got


@pytest.mark.asyncio
async def test_search_by_text(client, auth_tenant_id):
    ids = await _seed(
        auth_tenant_id,
        [
            ("a", None, "Здравствуйте, не приходит код в смс"),
            ("b", None, "Когда привезут заказ?"),
            ("c", None, "Спасибо за помощь"),
        ],
    )
    resp = await client.get("/api/v1/conversations?q=код")
    assert resp.status_code == 200
    got = [it["id"] for it in resp.json()["items"]]
    assert ids["a"] in got
    assert ids["b"] not in got
    assert ids["c"] not in got


@pytest.mark.asyncio
async def test_search_case_insensitive(client, auth_tenant_id):
    ids = await _seed(
        auth_tenant_id,
        [
            ("a", None, "ОПЛАТА не прошла"),
            ("b", None, "просто текст"),
        ],
    )
    resp = await client.get("/api/v1/conversations?q=оплата")
    assert resp.status_code == 200
    got = [it["id"] for it in resp.json()["items"]]
    assert ids["a"] in got
    assert ids["b"] not in got


@pytest.mark.asyncio
async def test_search_combined_with_tag(client, auth_tenant_id):
    ids = await _seed(
        auth_tenant_id,
        [
            ("match", ["оплата"], "не могу оплатить картой"),
            ("tag_no_match", ["оплата"], "когда привезут"),
            ("text_no_tag", None, "не могу оплатить картой"),
        ],
    )
    resp = await client.get("/api/v1/conversations?tags=оплата&q=оплатить")
    assert resp.status_code == 200
    got = [it["id"] for it in resp.json()["items"]]
    assert got == [ids["match"]]


@pytest.mark.asyncio
async def test_search_min_length(client, auth_tenant_id):
    """q короче 2 символов — 422 (Pydantic min_length)."""
    await _seed(auth_tenant_id, [("a", None, "test")])
    resp = await client.get("/api/v1/conversations?q=x")
    assert resp.status_code == 422
