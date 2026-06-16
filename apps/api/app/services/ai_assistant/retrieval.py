"""Retrieval для AI-ассистента: tenant-safe семантический поиск по сообщениям.

Эмбеддим вопрос пользователя той же моделью, что и сообщения
(`app.nlp.embeddings.encode_batch`), ищем ближайшие сообщения через pgvector
`<=>` (cosine), затем группируем их по диалогам и собираем для каждого
summary + найденные сниппеты. Источники возвращаются с conversation_id,
чтобы ассистент мог их цитировать, а фронт — поставить ссылку на /inbox/:id.

Ключевой инвариант безопасности: КАЖДЫЙ запрос фильтруется по tenant_id —
один tenant не может достать диалоги другого. См. тест tenant-изоляции.

Доступно только на Postgres с pgvector. На SQLite (тесты) и без torch-модели
возвращаем `available=False`, чтобы вызывающий код мог graceful-degrade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.nlp.embeddings import encode_batch

logger = logging.getLogger(__name__)


@dataclass
class RetrievedConversation:
    conversation_id: str
    title: str
    summary: str | None
    snippets: list[str] = field(default_factory=list)
    # Лучшая (минимальная) cosine-distance среди сообщений диалога.
    distance: float = 2.0

    @property
    def similarity(self) -> float:
        # Для нормализованных векторов distance ∈ [0,2] → similarity ∈ [-1,1].
        return 1.0 - self.distance


@dataclass
class RetrievalResult:
    available: bool
    reason: str | None = None
    items: list[RetrievedConversation] = field(default_factory=list)


def _embed_query(query: str) -> list[float] | None:
    vecs = encode_batch([query])
    if not vecs:
        return None
    return vecs[0]


def _vector_literal(vec: list[float]) -> str:
    # Сериализуем в строковый литерал pgvector '[v1,v2,...]' — так не зависим
    # от регистрации asyncpg-codec'а (тот же приём, что в /conversations/similar).
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


async def retrieve_context(
    session: AsyncSession,
    tenant_id: str,
    query: str,
) -> RetrievalResult:
    """Возвращает релевантные диалоги tenant'а для вопроса пользователя."""
    dialect = session.bind.dialect.name if session.bind else ""
    if dialect != "postgresql":
        return RetrievalResult(available=False, reason="vector_search_unavailable")

    vec = _embed_query(query)
    if vec is None:
        return RetrievalResult(available=False, reason="embeddings_unavailable")

    settings = get_settings()
    k = settings.ai_assistant_retrieval_k
    max_convs = settings.ai_assistant_max_convs

    # Top-K ближайших сообщений tenant'а. JOIN через conversations→integrations
    # даёт фильтр по tenant_id (изоляция). Берём только сообщения с эмбеддингом.
    sql = text(
        """
        SELECT m.conversation_id AS conv_id,
               m.text            AS snippet,
               m.embedding <=> CAST(:qvec AS vector) AS distance
          FROM messages m
          JOIN conversations c ON c.id = m.conversation_id
          JOIN integrations i ON i.id = c.integration_id
         WHERE i.tenant_id = :tenant_id
           AND m.embedding IS NOT NULL
           AND m.text IS NOT NULL
         ORDER BY distance ASC
         LIMIT :k
        """
    )
    rows = (
        await session.execute(
            sql,
            {"qvec": _vector_literal(vec), "tenant_id": tenant_id, "k": k},
        )
    ).all()
    if not rows:
        return RetrievalResult(available=True, items=[])

    # Группируем сниппеты по диалогам, сохраняя порядок появления (он же —
    # порядок близости, т.к. строки отсортированы по distance).
    by_conv: dict[str, RetrievedConversation] = {}
    for r in rows:
        conv = by_conv.get(r.conv_id)
        dist = float(r.distance)
        if conv is None:
            if len(by_conv) >= max_convs:
                continue
            conv = RetrievedConversation(
                conversation_id=r.conv_id, title="", summary=None, distance=dist
            )
            by_conv[r.conv_id] = conv
        if r.snippet and len(conv.snippets) < 3:
            conv.snippets.append(r.snippet.strip())

    # Подтягиваем title/summary одним запросом по собранным conv_id.
    # expanding=True разворачивает список в IN (:p1, :p2, ...).
    conv_ids = list(by_conv.keys())
    meta_sql = text(
        """
        SELECT c.id AS conv_id, c.contact_name AS contact_name, c.summary AS summary
          FROM conversations c
         WHERE c.id IN :conv_ids
        """
    ).bindparams(bindparam("conv_ids", expanding=True))
    meta_rows = (
        await session.execute(meta_sql, {"conv_ids": conv_ids})
    ).all()
    for r in meta_rows:
        conv = by_conv.get(r.conv_id)
        if conv is None:
            continue
        conv.title = (r.contact_name or "").strip() or f"Диалог {r.conv_id[:8]}"
        conv.summary = r.summary

    items = sorted(by_conv.values(), key=lambda c: c.distance)
    return RetrievalResult(available=True, items=items)
