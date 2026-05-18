"""Тесты исторического импорта Open Channels."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    Conversation,
    ConversationChannel,
    ImportJob,
    ImportJobStatus,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
    Message,
    SenderType,
)
from app.db.session import AsyncSessionLocal
from app.db.models import ConversationStatus
from app.integrations.bitrix24.importer import (
    _channel_from_entity_id,
    _session_is_closed,
    _session_meta,
    import_open_lines,
    run_import_job,
)


def test_session_meta_extracts_operator_and_line():
    operator, line = _session_meta(
        {"session": {"OPERATOR_ID": 42, "CONFIG_ID": "7"}}
    )
    assert operator == "42"
    assert line == "7"

    # Пустые/нулевые значения трактуем как «не задано».
    operator, line = _session_meta({"session": {"OPERATOR_ID": 0, "CONFIG_ID": ""}})
    assert operator is None
    assert line is None

    # Нет блока session — оба None.
    assert _session_meta({}) == (None, None)


def test_session_is_closed_by_status():
    """STATUS>=80 → закрыта; STATUS<80 или пусто → открыта."""
    assert _session_is_closed({"session": {"STATUS": 80}}) is True
    assert _session_is_closed({"session": {"STATUS": 90}}) is True
    assert _session_is_closed({"session": {"STATUS": 40}}) is False
    assert _session_is_closed({"session": {"STATUS": "25"}}) is False
    assert _session_is_closed({"session": {}}) is False
    assert _session_is_closed({}) is False
    # counter==0 в im.recent.get больше не должен влиять — это другой сигнал.
    assert _session_is_closed({"sessionId": 555}) is False


class FakeClient:
    """Заглушка BitrixClient.call для тестов импортера."""

    def __init__(self, responses: dict[str, object]):
        self._responses = responses
        self.calls: list[tuple[str, dict | None]] = []

    async def call(self, method, params=None):
        self.calls.append((method, params))
        key = method
        if method == "imopenlines.session.history.get" and params:
            key = f"{method}:{params.get('CHAT_ID')}"
        return self._responses[key]


def _now_iso(offset_days: int = 0) -> str:
    return (datetime.now(UTC) - timedelta(days=offset_days)).isoformat()


async def _make_integration(tenant_id: str | None = None) -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_imp",
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="Imp",
            domain="portal.bitrix24.ru",
            status=IntegrationStatus.connected,
            access_token="access-x",
            refresh_token="refresh-x",
        )
        session.add(integration)
        await session.commit()
        return integration.id


def test_channel_from_entity_id():
    assert _channel_from_entity_id("livechat|22|1|587") == ConversationChannel.livechat
    assert _channel_from_entity_id("imol|telegrambot|1|22") == ConversationChannel.telegram
    assert _channel_from_entity_id("imol|wazzup24|1|22") == ConversationChannel.whatsapp
    assert _channel_from_entity_id(None) == ConversationChannel.other
    assert _channel_from_entity_id("unknown") == ConversationChannel.other


@pytest.mark.asyncio
async def test_import_creates_conversation_and_messages(client):  # noqa: ARG001 — нужен сетап БД
    integration_id = await _make_integration()
    history_chat_1 = {
        "chatId": 1001,
        "sessionId": 555,
        "message": {
            "100": {
                "id": "100",
                "senderid": "0",
                "date": _now_iso(0),
                "text": "Системное событие",
            },
            "101": {
                "id": "101",
                "senderid": "200",
                "date": _now_iso(0),
                "text": "Привет от клиента",
            },
            "102": {
                "id": "102",
                "senderid": "300",
                "date": _now_iso(0),
                "text": "Здравствуйте, чем помочь?",
            },
        },
        "users": {
            "200": {"id": "200", "name": "Иван", "connector": True},
            "300": {"id": "300", "name": "Оператор"},
        },
        "chat": {
            "1001": {
                "id": "1001",
                "name": "Иван — Линия",
                "entityId": "imol|telegrambot|1|200",
            },
        },
    }
    fake = FakeClient(
        {
            "im.recent.get": [
                {
                    "chat_id": 1001,
                    "date_last_activity": _now_iso(0),
                    "counter": 0,
                },
                {
                    "chat_id": 1002,  # вне cutoff
                    "date_last_activity": _now_iso(200),
                },
            ],
            "imopenlines.session.history.get:1001": history_chat_1,
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        stats = await import_open_lines(fake, session, integration, days=30)

    assert stats.sessions == 1
    assert stats.messages == 3

    async with AsyncSessionLocal() as session:
        convs = (await session.execute(select(Conversation))).scalars().all()
        assert len(convs) == 1
        conv = convs[0]
        assert conv.external_id == "1001"
        assert conv.channel == ConversationChannel.telegram
        assert conv.contact_name == "Иван"
        assert conv.contact_external_id == "200"

        msgs = (
            await session.execute(
                select(Message).where(Message.conversation_id == conv.id)
            )
        ).scalars().all()
        assert len(msgs) == 3
        types = {m.sender_type for m in msgs}
        assert SenderType.client in types
        assert SenderType.agent in types
        assert SenderType.system in types


@pytest.mark.asyncio
async def test_import_is_idempotent(client):  # noqa: ARG001
    integration_id = await _make_integration()
    history = {
        "chatId": 5,
        "sessionId": 9,
        "message": {
            "1": {
                "id": "1",
                "senderid": "10",
                "date": _now_iso(0),
                "text": "hi",
            }
        },
        "users": {"10": {"id": "10", "name": "C", "connector": True}},
        "chat": {"5": {"id": "5", "entityId": "livechat|1|1|10"}},
    }
    fake = FakeClient(
        {
            "im.recent.get": [{"chat_id": 5, "date_last_activity": _now_iso(0)}],
            "imopenlines.session.history.get:5": history,
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake, session, integration, days=30)
        await import_open_lines(fake, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        convs = (await session.execute(select(Conversation))).scalars().all()
        msgs = (await session.execute(select(Message))).scalars().all()
        assert len(convs) == 1
        assert len(msgs) == 1


@pytest.mark.asyncio
async def test_active_session_stays_open_when_unread_zero(client):  # noqa: ARG001
    """Активный диалог (counter==0, нет session.STATUS>=80) остаётся open."""
    integration_id = await _make_integration()
    history = {
        "chatId": 77,
        "sessionId": 777,
        "session": {"STATUS": 40},  # активная сессия
        "message": {
            "1": {"id": "1", "senderid": "10", "date": _now_iso(0), "text": "hi"}
        },
        "users": {"10": {"id": "10", "name": "C", "connector": True}},
        "chat": {"77": {"id": "77", "entityId": "livechat|1|1|10"}},
    }
    fake = FakeClient(
        {
            "im.recent.get": [
                {"chat_id": 77, "date_last_activity": _now_iso(0), "counter": 0}
            ],
            "imopenlines.session.history.get:77": history,
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        conv = (await session.execute(select(Conversation))).scalar_one()
        assert conv.status == ConversationStatus.open


@pytest.mark.asyncio
async def test_reopens_conversation_when_status_drops(client):  # noqa: ARG001
    """Если ранее закрытый диалог снова стал активным — статус возвращается в open."""
    integration_id = await _make_integration()
    base = {
        "chatId": 88,
        "sessionId": 888,
        "message": {
            "1": {"id": "1", "senderid": "10", "date": _now_iso(0), "text": "hi"}
        },
        "users": {"10": {"id": "10", "name": "C", "connector": True}},
        "chat": {"88": {"id": "88", "entityId": "livechat|1|1|10"}},
    }

    # 1-й проход: закрытая сессия.
    fake1 = FakeClient(
        {
            "im.recent.get": [{"chat_id": 88, "date_last_activity": _now_iso(0)}],
            "imopenlines.session.history.get:88": {**base, "session": {"STATUS": 80}},
        }
    )
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake1, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        conv = (await session.execute(select(Conversation))).scalar_one()
        assert conv.status == ConversationStatus.closed

    # 2-й проход: статус стал активным — диалог должен переоткрыться.
    fake2 = FakeClient(
        {
            "im.recent.get": [{"chat_id": 88, "date_last_activity": _now_iso(0)}],
            "imopenlines.session.history.get:88": {**base, "session": {"STATUS": 25}},
        }
    )
    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake2, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        conv = (await session.execute(select(Conversation))).scalar_one()
        assert conv.status == ConversationStatus.open


@pytest.mark.asyncio
async def test_import_computes_response_time_and_operator(client):  # noqa: ARG001
    """После импорта у диалога заполнены FRT, operator_id и line_id."""
    integration_id = await _make_integration()
    base_ts = datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)

    def iso(seconds: int) -> str:
        return (base_ts + timedelta(seconds=seconds)).isoformat()

    history = {
        "chatId": 42,
        "sessionId": 4242,
        "session": {"STATUS": 40, "OPERATOR_ID": "99", "CONFIG_ID": "3"},
        "message": {
            "1": {
                "id": "1",
                "senderid": "200",
                "date": iso(0),
                "text": "клиент пишет",
            },
            # 90 секунд спустя — первый ответ оператора.
            "2": {
                "id": "2",
                "senderid": "99",
                "date": iso(90),
                "text": "оператор отвечает",
            },
            "3": {
                "id": "3",
                "senderid": "200",
                "date": iso(150),
                "text": "клиент ещё",
            },
        },
        "users": {
            "200": {"id": "200", "name": "Клиент", "connector": True},
            "99": {"id": "99", "name": "Оператор"},
        },
        "chat": {"42": {"id": "42", "entityId": "livechat|1|1|200"}},
    }
    fake = FakeClient(
        {
            "im.recent.get": [{"chat_id": 42, "date_last_activity": _now_iso(0)}],
            "imopenlines.session.history.get:42": history,
        }
    )

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        await import_open_lines(fake, session, integration, days=30)

    async with AsyncSessionLocal() as session:
        conv = (await session.execute(select(Conversation))).scalar_one()
        assert conv.assigned_user_id == "99"
        assert conv.line_id == "3"
        assert conv.first_message_at is not None
        assert conv.first_agent_reply_at is not None
        assert conv.response_time_sec == 90


@pytest.mark.asyncio
async def test_run_import_job_marks_done(client):  # noqa: ARG001
    integration_id = await _make_integration()
    fake = FakeClient({"im.recent.get": []})

    async with AsyncSessionLocal() as session:
        integration = await session.get(Integration, integration_id)
        job = ImportJob(id="imp_test", integration_id=integration_id, days=7)
        session.add(job)
        await session.commit()
        await run_import_job(fake, session, job, integration)

    async with AsyncSessionLocal() as session:
        job = await session.get(ImportJob, "imp_test")
        assert job.status == ImportJobStatus.done
        assert job.finished_at is not None
        assert job.processed_sessions == 0


@pytest.mark.asyncio
async def test_trigger_import_endpoint_creates_job(client, auth_tenant_id):
    # Создаём интеграцию напрямую, чтобы не зависеть от OAuth-flow.
    integration_id = await _make_integration(tenant_id=auth_tenant_id)

    resp = await client.post(
        f"/api/v1/integrations/{integration_id}/import?days=5"
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["integration_id"] == integration_id
    assert body["days"] == 5
    assert body["status"] == "pending"

    list_resp = await client.get(
        f"/api/v1/integrations/{integration_id}/import-jobs"
    )
    assert list_resp.status_code == 200
    jobs = list_resp.json()
    assert len(jobs) >= 1
    assert jobs[0]["id"] == body["id"]
