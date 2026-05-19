"""Тест дельта-sync'а CRM-сущностей: статус сделки обновляется без активности диалогов."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis

from app.db.models import (
    Conversation,
    ConversationChannel,
    ConversationStatus,
    CrmEntity,
    CrmEntityKind,
    CrmStageSemantics,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
)
from app.db.session import AsyncSessionLocal
from app.workers.tasks.crm_sync import sync_crm_for_integration


class _FakeClient:
    """BitrixClient mock: после «перехода в won» отдаёт обновлённую сделку."""

    def __init__(self) -> None:
        self.deal_stage_id = "WON"
        self.calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN001
        return None

    async def call(self, method, params=None):
        self.calls.append(method)
        if method == "crm.status.list":
            return [
                {"STATUS_ID": "NEW", "SEMANTICS": None, "NAME": "Новая", "SORT": 1},
                {"STATUS_ID": "WON", "SEMANTICS": "S", "NAME": "Won", "SORT": 99},
                {"STATUS_ID": "LOSE", "SEMANTICS": "F", "NAME": "Lost", "SORT": 100},
            ]
        if method == "crm.deal.list":
            return [
                {
                    "ID": "55",
                    "TITLE": "Сделка",
                    "STAGE_ID": self.deal_stage_id,
                    "OPPORTUNITY": "150000",
                    "CURRENCY_ID": "RUB",
                    "CLOSED": "Y" if self.deal_stage_id == "WON" else "N",
                }
            ]
        return []


@pytest.fixture
def patch_bitrix(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(
        "app.workers.tasks.crm_sync.BitrixClient", lambda *_a, **_k: fake
    )
    return fake


async def _seed_integration_with_in_progress_deal() -> str:
    """Готовит интеграцию с одной сделкой в статусе in_progress (как было
    при первом импорте, когда сделка ещё не закрыта)."""
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_crmsync",
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="X",
            domain="x.bitrix24.ru",
            status=IntegrationStatus.connected,
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(integration)
        await session.flush()

        conv = Conversation(
            id="c_open",
            integration_id=integration.id,
            external_id="ext_c",
            channel=ConversationChannel.telegram,
            status=ConversationStatus.closed,
        )
        deal = CrmEntity(
            id="crm_55",
            integration_id=integration.id,
            kind=CrmEntityKind.deal,
            external_id="55",
            stage_external_id="NEW",
            status_semantics=CrmStageSemantics.in_progress,
        )
        session.add_all([conv, deal])
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_sync_updates_deal_status_when_chat_is_silent(
    client, patch_bitrix  # noqa: ARG001
):
    """Если сделка закрылась в CRM, а в чате тишина — sync_crm_for_integration
    должен подтянуть STAGE_ID=WON и обновить status_semantics=won."""
    integration_id = await _seed_integration_with_in_progress_deal()
    redis = FakeRedis()
    try:
        ctx = {"redis": redis}
        result = await sync_crm_for_integration(ctx, integration_id)
    finally:
        await redis.aclose()

    assert result["updated"] == 1
    assert result["skipped"] == 0

    async with AsyncSessionLocal() as session:
        deal = await session.get(CrmEntity, "crm_55")
        assert deal.stage_external_id == "WON"
        assert deal.status_semantics == CrmStageSemantics.won
        assert float(deal.amount) == 150000.0
        assert deal.currency == "RUB"


@pytest.mark.asyncio
async def test_sync_skips_when_lock_held(client, patch_bitrix):  # noqa: ARG001
    integration_id = await _seed_integration_with_in_progress_deal()
    redis = FakeRedis()
    try:
        from app.workers.locks import lock_key

        await redis.set(lock_key(integration_id), "other", nx=True, ex=60)
        ctx = {"redis": redis}
        result = await sync_crm_for_integration(ctx, integration_id)
    finally:
        await redis.aclose()

    assert result["skipped"] == 1
    assert result["updated"] == 0


@pytest.mark.asyncio
async def test_sync_noop_when_no_entities(client, patch_bitrix):  # noqa: ARG001
    """Если у интеграции нет ни одной CrmEntity — задача отрабатывает 0
    без обращений к Bitrix24 (бережём rate limit)."""
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_empty",
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="E",
            domain="e.bitrix24.ru",
            status=IntegrationStatus.connected,
            access_token="a",
            refresh_token="r",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(integration)
        await session.commit()
        integration_id = integration.id

    redis = FakeRedis()
    try:
        ctx = {"redis": redis}
        result = await sync_crm_for_integration(ctx, integration_id)
    finally:
        await redis.aclose()

    assert result["updated"] == 0
    # Никаких REST-запросов — у нас нет сущностей, дёргать crm.* незачем.
    assert patch_bitrix.calls == []
