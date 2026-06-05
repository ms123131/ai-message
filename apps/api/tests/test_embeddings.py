"""Тесты эмбеддингов сообщений и семантического поиска (фаза 6.5).

sentence-transformers не качаем — заменяем `encode_batch` на детерминированный
stub, который превращает текст в 384-мерный вектор по hash'у слов. Этого
достаточно, чтобы покрыть SQL-логику и API-контракт. Реальная модель
проверяется руками после деплоя.

Семантический поиск (`<=>` на pgvector) на SQLite не работает —
эндпоинт `similar` возвращает `available=False`. Тестируем именно этот
graceful-degrade.
"""

from __future__ import annotations

import hashlib
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
from app.db.types import EMBEDDING_DIM
from app.nlp import embeddings as emb_mod
from app.nlp.embeddings import analyze_messages_embeddings_batch


def _stub_encode(texts: list[str]) -> list[list[float]]:
    """Детерминированный псевдо-эмбеддинг: hash → разложение по dim."""
    out = []
    for text in texts:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        # 32 байта → 384 float'а через повтор. L2-нормализация в конце.
        raw = []
        for i in range(EMBEDDING_DIM):
            raw.append(((h[i % len(h)] / 255.0) - 0.5))
        norm = sum(x * x for x in raw) ** 0.5 or 1.0
        out.append([x / norm for x in raw])
    return out


async def _seed_messages(
    tenant_id: str, texts: list[tuple[str, SenderType]]
) -> tuple[str, str, list[str]]:
    integration_id = f"intg_emb_{secrets.token_urlsafe(3)}"
    conv_id = f"cnv_emb_{secrets.token_urlsafe(3)}"
    now = datetime.now(UTC)
    msg_ids: list[str] = []
    async with AsyncSessionLocal() as session:
        session.add(
            Integration(
                id=integration_id,
                tenant_id=tenant_id,
                kind=IntegrationKind.bitrix24,
                mode=IntegrationMode.oauth,
                label="Emb",
                domain="emb.bitrix24.ru",
                status=IntegrationStatus.connected,
            )
        )
        session.add(
            Conversation(
                id=conv_id,
                integration_id=integration_id,
                external_id="ext-emb",
                channel=ConversationChannel.whatsapp,
                status=ConversationStatus.open,
            )
        )
        for i, (text, sender) in enumerate(texts):
            mid = f"mem_{secrets.token_urlsafe(3)}"
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
async def test_analyze_batch_writes_embeddings(
    client, auth_tenant_id, monkeypatch
):
    monkeypatch.setattr(emb_mod, "encode_batch", _stub_encode)

    _, _, msg_ids = await _seed_messages(
        auth_tenant_id,
        [
            ("Привет, помогите с заказом", SenderType.client),
            ("Конечно, что случилось?", SenderType.agent),
            ("", SenderType.client),  # пустой → нулевой вектор без encode
        ],
    )

    async with AsyncSessionLocal() as session:
        n = await analyze_messages_embeddings_batch(session, msg_ids)
        await session.commit()
    # 2 непустых + 1 пустой (нулевой вектор) — все три помечены обработанными
    assert n == 3

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(Message).where(Message.id.in_(msg_ids)))
        ).scalars().all()
        for m in rows:
            assert m.embedding is not None
            assert len(m.embedding) == EMBEDDING_DIM
            assert m.embedding_at is not None


@pytest.mark.asyncio
async def test_analyze_batch_skips_already_embedded(
    client, auth_tenant_id, monkeypatch
):
    monkeypatch.setattr(emb_mod, "encode_batch", _stub_encode)

    _, _, msg_ids = await _seed_messages(
        auth_tenant_id, [("test", SenderType.client)]
    )
    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        msg.embedding = [0.1] * EMBEDDING_DIM
        msg.embedding_at = datetime.now(UTC)
        await session.commit()

    async with AsyncSessionLocal() as session:
        n = await analyze_messages_embeddings_batch(session, msg_ids)
        await session.commit()
    assert n == 0


@pytest.mark.asyncio
async def test_analyze_batch_falls_back_when_model_unavailable(
    client, auth_tenant_id, monkeypatch
):
    # encode_batch вернул None — модель недоступна. Сообщения должны
    # остаться pending, без записи мусора в embedding.
    monkeypatch.setattr(emb_mod, "encode_batch", lambda texts: None)

    _, _, msg_ids = await _seed_messages(
        auth_tenant_id, [("hello world", SenderType.client)]
    )
    async with AsyncSessionLocal() as session:
        n = await analyze_messages_embeddings_batch(session, msg_ids)
        await session.commit()
    assert n == 0

    async with AsyncSessionLocal() as session:
        msg = await session.get(Message, msg_ids[0])
        assert msg.embedding is None


@pytest.mark.asyncio
async def test_analyze_embeddings_endpoint_enqueues(
    client, auth_tenant_id, _stub_arq_pool
):
    integration_id, _, _ = await _seed_messages(
        auth_tenant_id, [("hello", SenderType.client)]
    )
    resp = await client.post(
        f"/api/v1/integrations/{integration_id}/analyze-embeddings?batch_size=50"
    )
    assert resp.status_code == 202, resp.text
    names = [name for name, _, _ in _stub_arq_pool.enqueued]
    assert "embed_messages_for_integration" in names


@pytest.mark.asyncio
async def test_similar_endpoint_graceful_on_sqlite(client, auth_tenant_id):
    """На SQLite (тестовая БД) pgvector недоступен — эндпоинт должен
    отдавать available=False, а не падать с 500."""
    _, conv_id, _ = await _seed_messages(
        auth_tenant_id, [("hello", SenderType.client)]
    )
    resp = await client.get(f"/api/v1/conversations/{conv_id}/similar")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is False
    assert body["items"] == []


@pytest.mark.asyncio
async def test_nlp_cron_dispatches_embeddings(monkeypatch, auth_tenant_id):
    """nlp_dispatch_cron должен ставить и embed-таску на каждую интеграцию."""
    from app.config import get_settings
    from app.workers.tasks.nlp_cron import nlp_dispatch_cron

    settings = get_settings()
    monkeypatch.setattr(settings, "nlp_cron_interval_minutes", 5)

    integration_id, _, _ = await _seed_messages(
        auth_tenant_id, [("hello", SenderType.client)]
    )

    enqueued: list[tuple[str, tuple]] = []

    class _Pool:
        async def enqueue_job(self, name, *args, **kwargs):  # noqa: ARG002
            enqueued.append((name, args))

    res = await nlp_dispatch_cron({"redis": _Pool()})
    names = [n for n, _ in enqueued]
    assert "embed_messages_for_integration" in names
    # На одну интеграцию — 4 джоба (sentiment+tags+entities+embeddings).
    by_integration = [a for n, a in enqueued if a and a[0] == integration_id]
    assert len(by_integration) == 4
    assert res["integrations"] >= 1
