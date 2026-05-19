"""Тесты CRM-привязок: парсинг session.crm, enrichment, /dashboard/funnel."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    ConversationCrmLink,
    CrmEntity,
    CrmEntityKind,
    CrmStageSemantics,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
    PortalStage,
)
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.crm import extract_crm_refs_from_session
from app.integrations.bitrix24.importer import import_open_lines


def test_extract_crm_refs_single_fields():
    refs = extract_crm_refs_from_session(
        {"session": {"CRM_ENTITY_TYPE": "DEAL", "CRM_ENTITY_ID": "42"}}
    )
    assert refs == [(CrmEntityKind.deal, "42")]


def test_extract_crm_refs_dict_form():
    refs = extract_crm_refs_from_session(
        {"session": {"CRM": {"LEAD": ["10", "11"], "DEAL": "99"}}}
    )
    # Уникальные пары, сохраняем порядок появления.
    assert set(refs) == {
        (CrmEntityKind.lead, "10"),
        (CrmEntityKind.lead, "11"),
        (CrmEntityKind.deal, "99"),
    }


def test_extract_crm_refs_array_form_dedup():
    refs = extract_crm_refs_from_session(
        {
            "session": {
                "crm_entities": [
                    {"ENTITY_TYPE": "DEAL", "ENTITY_ID": "1"},
                    {"ENTITY_TYPE": "DEAL", "ENTITY_ID": "1"},  # дубль
                    {"ENTITY_TYPE": "CONTACT", "ENTITY_ID": "5"},
                ]
            }
        }
    )
    assert set(refs) == {
        (CrmEntityKind.deal, "1"),
        (CrmEntityKind.contact, "5"),
    }


def test_extract_crm_refs_empty_when_no_session():
    assert extract_crm_refs_from_session({}) == []
    assert extract_crm_refs_from_session({"session": {}}) == []


class _FakeClientWithCrm:
    """FakeClient, поддерживающий crm.status.list / crm.deal.list etc."""

    def __init__(self, responses: dict[str, object]):
        self._responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    async def call(self, method, params=None):
        self.calls.append((method, params))
        key = method
        if method == "imopenlines.session.history.get" and params:
            key = f"{method}:{params.get('CHAT_ID')}"
        if key not in self._responses:
            # crm.* методы, которые мы не замокали — пустой список.
            return []
        return self._responses[key]


def _now_iso(offset_days: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=offset_days)).isoformat()


async def _make_integration(tenant_id: str | None = None) -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_crm",
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="CRM",
            domain="portal.bitrix24.ru",
            status=IntegrationStatus.connected,
            access_token="access-x",
            refresh_token="refresh-x",
        )
        session.add(integration)
        await session.commit()
        return integration.id


def _history(chat_id: int, *, crm: dict | None = None) -> dict:
    h = {
        "chatId": chat_id,
        "session": {"STATUS": 80},
        "message": {
            "1": {
                "id": "1",
                "senderid": "200",
                "date": _now_iso(0),
                "text": "hi",
            }
        },
        "users": {"200": {"id": "200", "name": "Иван", "connector": True}},
        "chat": {str(chat_id): {"id": str(chat_id), "entityId": "imol|telegrambot|1|200"}},
    }
    if crm is not None:
        h["session"].update(crm)
    return h


@pytest.mark.asyncio
async def test_import_links_crm_entities_and_enriches(client):  # noqa: ARG001
    integration_id = await _make_integration()
    fake = _FakeClientWithCrm(
        {
            "im.recent.get": [
                {"chat_id": 200, "date_last_activity": _now_iso(0)},
            ],
            "imopenlines.session.history.get:200": _history(
                200, crm={"CRM": {"DEAL": ["42"], "CONTACT": ["7"]}}
            ),
            # Справочник стадий сделок.
            "crm.status.list": [
                {"STATUS_ID": "NEW", "SEMANTICS": None, "NAME": "Новая", "SORT": 10},
                {"STATUS_ID": "WON", "SEMANTICS": "S", "NAME": "Выиграна", "SORT": 999},
                {"STATUS_ID": "LOSE", "SEMANTICS": "F", "NAME": "Проиграна", "SORT": 9999},
            ],
            "crm.deal.list": [
                {
                    "ID": "42",
                    "TITLE": "Большая сделка",
                    "STAGE_ID": "WON",
                    "OPPORTUNITY": "100000",
                    "CURRENCY_ID": "RUB",
                    "ASSIGNED_BY_ID": "5",
                    "CLOSED": "Y",
                    "CLOSEDATE": _now_iso(0),
                },
            ],
            "crm.contact.list": [
                {"ID": "7", "NAME": "Пётр", "LAST_NAME": "Иванов"},
            ],
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        entities = (
            await session.execute(select(CrmEntity).order_by(CrmEntity.kind))
        ).scalars().all()
        kinds = {e.kind: e for e in entities}
        assert CrmEntityKind.deal in kinds
        assert CrmEntityKind.contact in kinds
        deal = kinds[CrmEntityKind.deal]
        assert deal.external_id == "42"
        assert deal.title == "Большая сделка"
        assert deal.stage_external_id == "WON"
        assert deal.status_semantics == CrmStageSemantics.won
        assert float(deal.amount) == 100000.0
        assert deal.currency == "RUB"

        contact = kinds[CrmEntityKind.contact]
        assert contact.title == "Пётр Иванов"

        links = (await session.execute(select(ConversationCrmLink))).all()
        assert len(links) == 2

        stages = (await session.execute(select(PortalStage))).scalars().all()
        # WON и LOSE имеют семантику, NEW — in_progress.
        sem_by_id = {s.external_id: s.semantics for s in stages}
        assert sem_by_id["WON"] == CrmStageSemantics.won
        assert sem_by_id["LOSE"] == CrmStageSemantics.lost
        assert sem_by_id["NEW"] == CrmStageSemantics.in_progress


@pytest.mark.asyncio
async def test_import_idempotent_for_crm_links(client):  # noqa: ARG001
    integration_id = await _make_integration()
    history = _history(201, crm={"CRM_ENTITY_TYPE": "DEAL", "CRM_ENTITY_ID": "9"})
    fake = _FakeClientWithCrm(
        {
            "im.recent.get": [{"chat_id": 201, "date_last_activity": _now_iso(0)}],
            "imopenlines.session.history.get:201": history,
            "crm.status.list": [],
            "crm.deal.list": [],
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake, session, integration, days=30)
        await import_open_lines(fake, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        entities = (await session.execute(select(CrmEntity))).scalars().all()
        links = (await session.execute(select(ConversationCrmLink))).all()
        assert len(entities) == 1
        assert len(links) == 1


@pytest.mark.asyncio
async def test_dashboard_funnel_and_overview_kpis(client):  # noqa: ARG001
    """E2E: после импорта /dashboard/funnel и /overview отдают корректные цифры."""
    # Берём tenant из дефолтного теста-юзера.
    import jwt

    from app.config import get_settings

    settings = get_settings()
    tid = jwt.decode(
        client.headers["Authorization"].split(" ", 1)[1],
        settings.jwt_secret,
        algorithms=["HS256"],
    )["tid"]

    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_funnel",
            tenant_id=tid,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="F",
            domain="x.bitrix24.ru",
            status=IntegrationStatus.connected,
            access_token="a",
            refresh_token="r",
        )
        session.add(integration)
        await session.commit()
        integration_id = integration.id

    # Импортим 3 диалога: с won-сделкой, с lost-сделкой, без CRM.
    fake = _FakeClientWithCrm(
        {
            "im.recent.get": [
                {"chat_id": 301, "date_last_activity": _now_iso(0)},
                {"chat_id": 302, "date_last_activity": _now_iso(0)},
                {"chat_id": 303, "date_last_activity": _now_iso(0)},
            ],
            "imopenlines.session.history.get:301": _history(
                301, crm={"CRM": {"DEAL": ["100"]}}
            ),
            "imopenlines.session.history.get:302": _history(
                302, crm={"CRM": {"DEAL": ["200"]}}
            ),
            "imopenlines.session.history.get:303": _history(303),
            "crm.status.list": [
                {"STATUS_ID": "WON", "SEMANTICS": "S", "NAME": "Won", "SORT": 1},
                {"STATUS_ID": "LOSE", "SEMANTICS": "F", "NAME": "Lost", "SORT": 2},
            ],
            "crm.deal.list": [
                {
                    "ID": "100",
                    "TITLE": "W",
                    "STAGE_ID": "WON",
                    "OPPORTUNITY": "50000",
                    "CURRENCY_ID": "RUB",
                    "CLOSED": "Y",
                },
                {
                    "ID": "200",
                    "TITLE": "L",
                    "STAGE_ID": "LOSE",
                    "OPPORTUNITY": "0",
                    "CURRENCY_ID": "RUB",
                },
            ],
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake, session, integration, days=30)

    # /dashboard/funnel
    resp = await client.get("/api/v1/dashboard/funnel?days=30")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    stages = {s["key"]: s["count"] for s in data["stages"]}
    assert stages["conversations"] == 3
    assert stages["with_deal"] == 2
    assert stages["with_won_deal"] == 1
    assert stages["with_lost_deal"] == 1
    assert stages["with_lead"] == 0
    # 2/3 ≈ 66.67%
    assert abs(data["conversion_to_deal_pct"] - (2 / 3 * 100)) < 0.01
    assert abs(data["win_rate_pct"] - 50.0) < 0.01
    assert data["revenue_won"] == 50000.0
    assert data["currency"] == "RUB"

    # /dashboard/overview
    resp = await client.get("/api/v1/dashboard/overview?days=30")
    assert resp.status_code == 200, resp.text
    o = resp.json()
    assert abs(o["conversion_to_deal_pct"]["value"] - (2 / 3 * 100)) < 0.01
    assert abs(o["win_rate_pct"]["value"] - 50.0) < 0.01
