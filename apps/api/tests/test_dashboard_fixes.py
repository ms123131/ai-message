"""Тесты исправлений дашборда (fix/dashboard-quality):

- by-line: line_id из webhook, fallback name = "Channel · #N"
- sentiment: исключение Bitrix-служебных сообщений
- events.parse: line_id из payload
- CLI: cleanup-system-sentiment / mark-system-messages
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
    PortalLine,
    SenderType,
    Sentiment,
)
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.events import parse_openlines_message
from app.nlp.bitrix_system_text import is_bitrix_system_text

# ---------------------------------------------------------------------------
# is_bitrix_system_text — unit
# ---------------------------------------------------------------------------


def test_is_bitrix_system_text_detects_known_patterns():
    assert is_bitrix_system_text(
        "Начат новый диалог №[URL=/online/?IM_HISTORY=imol|8]8[/URL]"
    )
    assert is_bitrix_system_text(
        "Обращение направлено на [USER=12 REPLACE]Станислав Марин[/USER]"
    )
    assert is_bitrix_system_text("Закрыт диалог №[URL=...]7[/URL]")
    assert is_bitrix_system_text(
        "Оператор [USER=5]Анна[/USER] переадресовал диалог на [USER=7]"
    )


def test_is_bitrix_system_text_passes_regular_messages():
    assert not is_bitrix_system_text("Здравствуйте, нужна помощь")
    assert not is_bitrix_system_text("Спасибо за ответ!")
    assert not is_bitrix_system_text("")
    assert not is_bitrix_system_text(None)


# ---------------------------------------------------------------------------
# events.parse — line_id
# ---------------------------------------------------------------------------


def _base_payload() -> dict[str, str]:
    return {
        "event": "ONOPENLINEMESSAGEADD",
        "auth[domain]": "test.bitrix24.ru",
        "auth[member_id]": "m-1",
        "data[DATA][0][chat][id]": "100",
        "data[DATA][0][message][text]": "Hi",
        "data[DATA][0][message][id]": "555",
        "data[DATA][0][message][user_id]": "10",
        "data[DATA][0][connector][connector_id]": "telegram",
        "data[DATA][0][connector][chat_id]": "ext-100",
        "data[DATA][0][connector][user_id]": "10",
    }


def test_parse_openlines_extracts_line_id():
    p = _base_payload()
    p["data[DATA][0][connector][line_id]"] = "42"
    ev = parse_openlines_message(p)
    assert ev is not None
    assert ev.line_id == "42"
    assert ev.channel == ConversationChannel.telegram


def test_parse_openlines_line_id_optional():
    ev = parse_openlines_message(_base_payload())
    assert ev is not None
    assert ev.line_id is None


# ---------------------------------------------------------------------------
# by-line: fallback name + line_id из webhook
# ---------------------------------------------------------------------------


async def _seed_lines(tenant_id: str) -> str:
    """Сидит integration с тремя диалогами: telegram без PortalLine.name,
    livechat с известным именем, и whatsapp с line_id=NULL (должен выпасть).
    """
    integration_id = f"intg_lines_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Lines",
                domain="lines.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        # Линия с известным именем
        session.add(
            PortalLine(
                id="pl_named",
                integration_id=integration_id,
                external_id="11",
                name="Сайт продаж",
                is_active=True,
                last_synced_at=now,
            )
        )
        # Линия без записи в PortalLine — line_id=22, telegram → fallback "Telegram · #22"
        session.add(
            Conversation(
                id="c_tg",
                integration_id=integration_id,
                external_id="ext_tg",
                channel=ConversationChannel.telegram,
                line_id="22",
                status=ConversationStatus.open,
                created_at=now - timedelta(hours=1),
            )
        )
        session.add(
            Conversation(
                id="c_lc",
                integration_id=integration_id,
                external_id="ext_lc",
                channel=ConversationChannel.livechat,
                line_id="11",
                status=ConversationStatus.open,
                created_at=now - timedelta(hours=2),
            )
        )
        # Сообщения, чтобы линии оказались в выдаче
        for cid in ("c_tg", "c_lc"):
            session.add(
                Message(
                    id=f"m_{cid}",
                    conversation_id=cid,
                    sender_type=SenderType.client,
                    text="hi",
                    sent_at=now - timedelta(minutes=10),
                )
            )
        await session.commit()
    return integration_id


@pytest.mark.asyncio
async def test_by_line_fallback_name_uses_channel(client, auth_tenant_id):
    await _seed_lines(auth_tenant_id)
    resp = await client.get("/api/v1/dashboard/by-line?days=7")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    by_id = {r["line_id"]: r for r in rows}
    # Известное имя — берём из PortalLine
    assert by_id["11"]["name"] == "Сайт продаж"
    # Без PortalLine — fallback по каналу
    assert by_id["22"]["name"] == "Telegram · #22"


# ---------------------------------------------------------------------------
# sentiment dashboard: фильтр служебных сообщений
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_sentiment_excludes_bitrix_system(client, auth_tenant_id):
    """Служебные тексты Bitrix не должны попадать в total_messages KPI."""
    integration_id = f"intg_sys_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=auth_tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Sys",
                domain="sys.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        conv_id = "c_sys"
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-sys",
                channel=ConversationChannel.telegram,
                status=ConversationStatus.open,
            )
        )
        # 1 настоящее клиентское + 2 служебных, обе как client (как иногда
        # приходит из Bitrix), все без sentiment.
        session.add(
            Message(
                id="m_real",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Здравствуйте, нужна помощь",
                sent_at=now - timedelta(minutes=5),
            )
        )
        session.add(
            Message(
                id="m_sys1",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Начат новый диалог №[URL=/online/?IM_HISTORY=imol|8]8[/URL]",
                sent_at=now - timedelta(minutes=10),
            )
        )
        session.add(
            Message(
                id="m_sys2",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Обращение направлено на [USER=12 REPLACE]Станислав[/USER]",
                sent_at=now - timedelta(minutes=11),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/dashboard/sentiment?days=7")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_messages"] == 1  # только m_real
    assert body["pending_messages"] == 1


# ---------------------------------------------------------------------------
# CLI: cleanup-system-sentiment + mark-system-messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cli_cleanup_system_sentiment(client, auth_tenant_id):
    integration_id = f"intg_cli_{secrets.token_urlsafe(3)}"
    conv_id = "c_cli"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=auth_tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Cli",
                domain="cli.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-cli",
                channel=ConversationChannel.whatsapp,
                status=ConversationStatus.open,
                sentiment_score=-0.5,
            )
        )
        session.add(
            Message(
                id="m_cli_sys",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Начат новый диалог №[URL=...]1[/URL]",
                sent_at=now,
                sentiment=Sentiment.neutral,
                sentiment_at=now,
                sentiment_model="stub",
            )
        )
        session.add(
            Message(
                id="m_cli_real",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Это плохо",
                sent_at=now,
                sentiment=Sentiment.negative,
                sentiment_at=now,
                sentiment_model="stub",
            )
        )
        await session.commit()

    from app.cli import _cmd_cleanup_system_sentiment

    rc = await _cmd_cleanup_system_sentiment(integration_id)
    assert rc == 0

    async with AsyncSessionLocal() as session:
        sys_msg = await session.get(Message, "m_cli_sys")
        real_msg = await session.get(Message, "m_cli_real")
        conv = await session.get(Conversation, conv_id)
        assert sys_msg.sentiment is None
        assert sys_msg.sentiment_at is None
        # Реальное негативное сообщение остаётся
        assert real_msg.sentiment == Sentiment.negative
        # Score диалога пересчитан только по реальным → -1.0
        assert conv.sentiment_score == pytest.approx(-1.0)


@pytest.mark.asyncio
async def test_cli_mark_system_messages(client, auth_tenant_id):
    integration_id = f"intg_mark_{secrets.token_urlsafe(3)}"
    conv_id = "c_mark"
    now = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=auth_tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Mark",
                domain="mark.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-mark",
                channel=ConversationChannel.telegram,
                status=ConversationStatus.open,
            )
        )
        session.add(
            Message(
                id="m_mark_sys",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Закрыт диалог №[URL=...]5[/URL]",
                sent_at=now,
            )
        )
        session.add(
            Message(
                id="m_mark_real",
                conversation_id=conv_id,
                sender_type=SenderType.client,
                text="Спасибо",
                sent_at=now,
            )
        )
        await session.commit()

    from app.cli import _cmd_mark_system_messages

    rc = await _cmd_mark_system_messages(integration_id)
    assert rc == 0

    async with AsyncSessionLocal() as session:
        sys_msg = await session.get(Message, "m_mark_sys")
        real_msg = await session.get(Message, "m_mark_real")
        assert sys_msg.sender_type == SenderType.system
        assert real_msg.sender_type == SenderType.client
