"""Тесты извлечения сущностей (фаза 6.6).

Natasha не обязательна — её часть мокируем, чтобы CI не качал ~150мб моделей
и не падал на её отсутствии. Регулярки тестируем напрямую.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

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
from app.nlp.entities import (
    _extract_regex,
    _normalize_phone,
    _parse_money_amount,
    analyze_messages_entities_batch,
    extract_entities,
)

# ---------------------------------------------------------------------------
# Регулярки — unit
# ---------------------------------------------------------------------------


def test_extract_email():
    out = _extract_regex("Пишите на support@example.com и admin@test.RU.")
    assert out["email"] == ["admin@test.ru", "support@example.com"]


def test_extract_url():
    out = _extract_regex("Подробности: https://example.com/path?x=1 и www.foo.bar.")
    urls = out["url"]
    assert "https://example.com/path?x=1" in urls
    assert "www.foo.bar" in urls


def test_extract_phone_normalizes():
    text = "Звони +7 (999) 123-45-67 или 8 999 123 45 67 ещё 79991234567"
    out = _extract_regex(text)
    # Все три формы → один канонический номер
    assert out["phone"] == ["+79991234567"]


def test_normalize_phone_handles_dashes():
    assert _normalize_phone("8-999-123-45-67") == "+79991234567"
    assert _normalize_phone("+7 999 123 4567") == "+79991234567"


def test_extract_money_with_currency():
    text = "Стоимость 1 500 руб., было 2,500.99 USD, ещё 199₽"
    out = _extract_regex(text)
    pairs = {(m["amount"], m["currency"]) for m in out["money"]}
    assert (1500.0, "RUB") in pairs
    assert (2500.99, "USD") in pairs
    assert (199.0, "RUB") in pairs


def test_money_ignores_amount_without_currency():
    out = _extract_regex("Артикул 12345 и ещё 999.")
    assert "money" not in out


def test_parse_money_amount_variants():
    assert _parse_money_amount("1 500") == 1500.0
    assert _parse_money_amount("1,500.99") == 1500.99
    assert _parse_money_amount("1.500,99") == 1500.99
    assert _parse_money_amount("12,5") == 12.5
    assert _parse_money_amount("1,500") == 1500.0  # тысячи
    assert _parse_money_amount("abc") is None


def test_extract_tracking_with_hint():
    out = _extract_regex("Трек-номер: RU123456789CN, проверьте")
    assert "RU123456789CN" in out["tracking"]


def test_extract_tracking_ups_format():
    out = _extract_regex("Отправлено по UPS, номер 1Z999AA10123456784.")
    assert "1Z999AA10123456784" in out["tracking"]


def test_extract_empty_text():
    assert extract_entities("") == {}
    assert extract_entities("   ") == {}


def test_extract_natasha_optional(monkeypatch):
    """Если natasha не установлена — extract_entities возвращает только
    регулярки и не падает."""
    from app.nlp import entities as ent_mod

    monkeypatch.setattr(ent_mod, "_get_natasha", lambda: None)
    out = extract_entities("Иван Петров пишет с support@x.ru, телефон +79991112233")
    assert out["email"] == ["support@x.ru"]
    assert out["phone"] == ["+79991112233"]
    # person/location/organization — без NER не появляются
    assert "person" not in out


def test_extract_with_natasha_stub(monkeypatch):
    """Эмулируем Natasha, не загружая реальных моделей."""
    from app.nlp import entities as ent_mod

    class _Span:
        def __init__(self, type_, text):
            self.type = type_
            self.text = text

    class _FakeDoc:
        def __init__(self, text):
            self.text = text
            self.spans: list[_Span] = []

        def segment(self, *_):
            pass

        def tag_morph(self, *_):
            pass

        def tag_ner(self, *_):
            # Имя + город из стабильного теста
            if "Иван Петров" in self.text:
                self.spans.append(_Span("PER", "Иван Петров"))
            if "Москв" in self.text:
                self.spans.append(_Span("LOC", "Москве"))
            if "Сбер" in self.text:
                self.spans.append(_Span("ORG", "Сбербанк"))

    monkeypatch.setattr(
        ent_mod, "_get_natasha", lambda: (None, None, None, _FakeDoc)
    )
    out = extract_entities(
        "Иван Петров из Сбербанка в Москве, тел +79991110000"
    )
    assert out["person"] == ["Иван Петров"]
    assert out["organization"] == ["Сбербанк"]
    assert out["location"] == ["Москве"]
    assert out["phone"] == ["+79991110000"]


# ---------------------------------------------------------------------------
# Batch + БД
# ---------------------------------------------------------------------------


async def _seed_messages(
    tenant_id: str, texts: list[tuple[str, SenderType]]
) -> tuple[str, str, list[str]]:
    integration_id = f"intg_ent_{secrets.token_urlsafe(3)}"
    conv_id = f"cnv_ent_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    msg_ids: list[str] = []
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Ent",
                domain="ent.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-e",
                channel=ConversationChannel.whatsapp,
                status=ConversationStatus.open,
            )
        )
        for i, (text, sender) in enumerate(texts):
            mid = f"me_{secrets.token_urlsafe(3)}"
            msg_ids.append(mid)
            session.add(
                Message(
                    id=mid,
                    conversation_id=conv_id,
                    sender_type=sender,
                    text=text,
                    sent_at=now - timedelta(minutes=len(texts) - i),
                )
            )
        await session.commit()
    return integration_id, conv_id, msg_ids


@pytest.mark.asyncio
async def test_analyze_batch_writes_entities(client, auth_tenant_id, monkeypatch):
    from app.nlp import entities as ent_mod

    # NER выключаем — тест на regex-часть
    monkeypatch.setattr(ent_mod, "_get_natasha", lambda: None)

    _, _, msg_ids = await _seed_messages(
        auth_tenant_id,
        [
            ("Напишите на a@b.ru, тел +79990001122", SenderType.client),
            ("Спасибо!", SenderType.agent),
            ("Сумма к оплате 2500 руб.", SenderType.client),
        ],
    )
    async with AsyncSessionLocal() as session:
        n = await analyze_messages_entities_batch(session, msg_ids)
        await session.commit()
    assert n == 3

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(Message).where(Message.id.in_(msg_ids)))
        ).scalars().all()
        by_text = {m.text: m for m in rows}
        first = by_text["Напишите на a@b.ru, тел +79990001122"]
        assert first.entities["email"] == ["a@b.ru"]
        assert first.entities["phone"] == ["+79990001122"]
        assert first.entities_at is not None

        empty = by_text["Спасибо!"]
        # Ничего не найдено — записан пустой dict, не None
        assert empty.entities == {}
        assert empty.entities_at is not None

        money = by_text["Сумма к оплате 2500 руб."]
        assert money.entities["money"][0]["amount"] == 2500.0
        assert money.entities["money"][0]["currency"] == "RUB"


@pytest.mark.asyncio
async def test_analyze_batch_skips_already_processed(
    client, auth_tenant_id, monkeypatch
):
    from app.nlp import entities as ent_mod

    monkeypatch.setattr(ent_mod, "_get_natasha", lambda: None)

    _, _, msg_ids = await _seed_messages(
        auth_tenant_id, [("текст", SenderType.client)]
    )
    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        msg.entities = {"phone": ["+71111111111"]}
        msg.entities_at = datetime.now(UTC)
        await session.commit()

    async with AsyncSessionLocal() as session:
        n = await analyze_messages_entities_batch(session, msg_ids)
        await session.commit()
    assert n == 0

    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        assert msg.entities == {"phone": ["+71111111111"]}


@pytest.mark.asyncio
async def test_analyze_entities_endpoint_enqueues(
    client, auth_tenant_id, _stub_arq_pool
):
    integration_id, _, _ = await _seed_messages(
        auth_tenant_id, [("a@b.ru", SenderType.client)]
    )
    resp = await client.post(
        f"/api/v1/integrations/{integration_id}/analyze-entities?batch_size=100"
    )
    assert resp.status_code == 202, resp.text
    names = [name for name, _, _ in _stub_arq_pool.enqueued]
    assert "analyze_entities_for_integration" in names


@pytest.mark.asyncio
async def test_messages_api_exposes_entities(
    client, auth_tenant_id, monkeypatch
):
    from app.nlp import entities as ent_mod

    monkeypatch.setattr(ent_mod, "_get_natasha", lambda: None)

    _, conv_id, msg_ids = await _seed_messages(
        auth_tenant_id,
        [("Звоните +79991234567, заказ на 1500 руб", SenderType.client)],
    )
    async with AsyncSessionLocal() as session:
        await analyze_messages_entities_batch(session, msg_ids)
        await session.commit()

    resp = await client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert items
    msg = items[0]
    assert msg["entities"]["phone"] == ["+79991234567"]
    assert msg["entities"]["money"][0]["amount"] == 1500.0
