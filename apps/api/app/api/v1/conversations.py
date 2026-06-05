"""Read-API для диалогов и сообщений (фаза 3.5, минимум для end-to-end тестов)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._cursor import decode_cursor, encode_cursor
from app.auth.deps import get_current_user
from app.db import get_session
from app.db.models import Conversation, ConversationChannel, Integration, Message
from app.db.models import User as UserModel
from app.schemas.conversation import (
    ConversationListItem,
    ConversationOut,
    MessageOut,
)
from app.security.ratelimit import limiter

router = APIRouter(prefix="/conversations", tags=["conversations"])

# Порог тональности — согласован с фронтом (SentimentBadge): score за пределами
# ±SENTIMENT_THRESHOLD трактуется как positive/negative, между — neutral.
SENTIMENT_THRESHOLD = 0.2


@router.get("")
async def list_conversations(
    integration_id: str | None = None,
    channel: ConversationChannel | None = None,
    status_: str | None = Query(None, alias="status"),
    operator_id: str | None = None,
    line_id: str | None = None,
    sentiment: Literal["positive", "neutral", "negative"] | None = None,
    tags: list[str] | None = Query(
        None,
        description=(
            "Список slug'ов тем для фильтрации. Например ?tags=оплата&tags=доставка"
        ),
    ),
    tag_mode: Literal["any", "all"] = Query(
        "any",
        description=(
            "any — диалог попадает в выборку, если у него есть хотя бы один "
            "из указанных тегов; all — должны быть все."
        ),
    ),
    q: str | None = Query(
        None,
        min_length=2,
        max_length=200,
        description=(
            "Полнотекстовый поиск по сообщениям диалога. На Postgres — через "
            "tsvector + websearch_to_tsquery (русский конфиг). На SQLite — "
            "ILIKE fallback. Минимум 2 символа."
        ),
    ),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(
        None,
        description=(
            "Курсор для следующей страницы. Получи из `next_cursor` "
            "предыдущего ответа. Не комбинируй с offset."
        ),
    ),
    offset: int = Query(
        0,
        ge=0,
        description=(
            "DEPRECATED. Используется только для обратной совместимости со "
            "старым фронтом. Cursor-пагинация эффективнее на больших списках."
        ),
    ),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict:
    """Список диалогов tenant'а с cursor-пагинацией.

    Сортировка: `COALESCE(last_message_at, created_at) DESC, id DESC`.
    Денормализованные `last_message_at` и `last_message_preview` поддерживаются
    импортером/поллером/webhook'ом (см. фаза 7 — оптимизация Inbox).
    """
    # Ключ сортировки: для пустых диалогов берём created_at — иначе они
    # «провалятся в самый низ». Делаем явное coalesce в самом SELECT, чтобы
    # курсор работал на одной шкале.
    sort_key = func.coalesce(Conversation.last_message_at, Conversation.created_at).label(
        "sort_key"
    )

    stmt = (
        select(Conversation, sort_key)
        .join(Integration, Integration.id == Conversation.integration_id)
        .where(Integration.tenant_id == user.tenant_id)
        .order_by(desc(sort_key), desc(Conversation.id))
        .limit(limit + 1)  # +1 — чтобы понять, есть ли next_cursor
    )
    if integration_id:
        stmt = stmt.where(Conversation.integration_id == integration_id)
    if channel:
        stmt = stmt.where(Conversation.channel == channel)
    if status_ in ("open", "closed"):
        stmt = stmt.where(Conversation.status == status_)
    if operator_id:
        stmt = stmt.where(Conversation.assigned_user_id == operator_id)
    if line_id:
        stmt = stmt.where(Conversation.line_id == line_id)
    if sentiment == "negative":
        stmt = stmt.where(Conversation.sentiment_score < -SENTIMENT_THRESHOLD)
    elif sentiment == "positive":
        stmt = stmt.where(Conversation.sentiment_score > SENTIMENT_THRESHOLD)
    elif sentiment == "neutral":
        stmt = stmt.where(
            Conversation.sentiment_score >= -SENTIMENT_THRESHOLD,
            Conversation.sentiment_score <= SENTIMENT_THRESHOLD,
        )

    # Фильтр по тегам диалога (денормализованная Conversation.tags — JSON array
    # из объединённых тегов клиентских сообщений, см. recompute_conversation_tags).
    # На PG нативные операторы jsonb ?| (any) / ?& (all). На SQLite — нет json
    # contains-функции, используем JSON1 EXISTS через json_each.
    if tags:
        clean_tags = [t.strip() for t in tags if t and t.strip()]
        if clean_tags:
            dialect = session.bind.dialect.name if session.bind else "postgresql"
            if dialect == "postgresql":
                # tags::jsonb ?| array['a','b'] -> any; ?& -> all
                op = "?|" if tag_mode == "any" else "?&"
                stmt = stmt.where(
                    text(
                        f"CAST(conversations.tags AS jsonb) {op} :tags_arr"
                    ).bindparams(tags_arr=clean_tags)
                )
            else:
                # SQLite: для каждого тега ищем по json_each. ANY → OR, ALL → AND.
                # Не самый шустрый путь, но dev/test-режим — данных мало.
                combiner = or_ if tag_mode == "any" else and_
                conds = [
                    text(
                        f"EXISTS (SELECT 1 FROM json_each(conversations.tags) "
                        f"WHERE json_each.value = :tag_{i})"
                    ).bindparams(**{f"tag_{i}": t})
                    for i, t in enumerate(clean_tags)
                ]
                stmt = stmt.where(combiner(*conds))

    # Полнотекстовый поиск по сообщениям. Чтобы не выводить дубликаты
    # (диалог может иметь много совпадений), используем EXISTS-подзапрос.
    # PG: tsvector с russian-конфигом + websearch_to_tsquery (понимает кавычки,
    # OR, -минус). SQLite: ILIKE по text — не FTS, но как fallback для dev.
    if q:
        dialect = session.bind.dialect.name if session.bind else "postgresql"
        if dialect == "postgresql":
            search_exists = text(
                "EXISTS (SELECT 1 FROM messages m "
                "WHERE m.conversation_id = conversations.id "
                "AND m.tsv @@ websearch_to_tsquery('russian', :q))"
            ).bindparams(q=q)
        else:
            # SQLite COLLATE NOCASE — только ASCII. Для русского обходим
            # двойным LOWER() (для UTF-8 в SQLite это работает с ICU/sqlite3
            # по-разному, но базовая lower() для кириллицы работает корректно
            # на CPython 3.12+).
            like = f"%{q.lower()}%"
            search_exists = text(
                "EXISTS (SELECT 1 FROM messages m "
                "WHERE m.conversation_id = conversations.id "
                "AND LOWER(m.text) LIKE :q)"
            ).bindparams(q=like)
        stmt = stmt.where(search_exists)

    # Курсор: композитное (sort_key, id) < (cursor_at, cursor_id).
    # Если есть оба cursor и offset — приоритет у cursor (это новый путь).
    cursor_pair = decode_cursor(cursor)
    if cursor_pair is not None:
        cur_at, cur_id = cursor_pair
        if cur_at is not None:
            stmt = stmt.where(
                or_(
                    sort_key < cur_at,
                    and_(sort_key == cur_at, Conversation.id < cur_id),
                )
            )
        else:
            # Курсор от пустого диалога — пропускаем всё с sort_key <= NULL
            # (NULL быть не должен после coalesce, но защищаемся).
            stmt = stmt.where(Conversation.id < cur_id)
    elif offset > 0:
        stmt = stmt.offset(offset)

    rows = (await session.execute(stmt)).all()

    # Есть «лишняя» строка → есть следующая страница.
    has_more = len(rows) > limit
    page = rows[:limit]

    # Считаем message_count для страницы одним SELECT (GROUP BY).
    counts: dict[str, int] = {}
    if page:
        conv_ids = [c.id for c, _ in page]
        cnt_rows = (
            await session.execute(
                select(Message.conversation_id, func.count(Message.id))
                .where(Message.conversation_id.in_(conv_ids))
                .group_by(Message.conversation_id)
            )
        ).all()
        counts = {cid: int(cnt or 0) for cid, cnt in cnt_rows}

    items: list[dict] = []
    for conv, sort_at in page:
        items.append(
            {
                **ConversationListItem(
                    **ConversationOut.model_validate(conv).model_dump(),
                    message_count=counts.get(conv.id, 0),
                    last_message_at=conv.last_message_at,
                    last_message_preview=conv.last_message_preview,
                ).model_dump(mode="json"),
            }
        )

    next_cursor = None
    if has_more and page:
        last_conv, last_sort = page[-1]
        next_cursor = encode_cursor(last_sort, last_conv.id)

    return {"items": items, "next_cursor": next_cursor}


async def _get_owned_conv(
    session: AsyncSession, conversation_id: str, user: UserModel
) -> Conversation:
    obj = await session.get(Conversation, conversation_id)
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    integration = await session.get(Integration, obj.integration_id)
    if not integration or integration.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return obj


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> Conversation:
    return await _get_owned_conv(session, conversation_id, user)


@router.post(
    "/{conversation_id}/summarize",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("12/minute")
async def trigger_summarize(
    request: Request,  # noqa: ARG001 — нужен slowapi
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """Ставит LLM-резюме диалога в очередь. Smart-провайдер.

    Лимит 12/мин — пользователь не должен иметь возможность спамить smart-LLM
    кликами «Сводка» в Inbox. Это per-tenant лимит, не per-conversation.
    """
    from app.workers.redis_pool import get_pool

    await _get_owned_conv(session, conversation_id, user)
    pool = await get_pool()
    job = await pool.enqueue_job("summarize_conversation_task", conversation_id)
    return {
        "status": "accepted",
        "job_id": getattr(job, "job_id", "unknown"),
        "conversation_id": conversation_id,
    }


@router.get("/{conversation_id}/similar")
async def list_similar_conversations(
    conversation_id: str,
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict:
    """Семантически похожие диалоги (фаза 6.5).

    Берём центроид эмбеддингов сообщений исходного диалога (среднее по всем
    непустым векторам) и ищем диалоги того же tenant'а с минимальной
    cosine-distance до центроида. Группируем по conversation_id, берём
    минимальную дистанцию по сообщению (один близкий ответ — уже сигнал).

    Доступно только на Postgres с pgvector. На SQLite (тесты) возвращаем
    пустой список и `available=False`, чтобы фронт мог graceful-degrade.
    """
    await _get_owned_conv(session, conversation_id, user)

    dialect = session.bind.dialect.name if session.bind else ""
    if dialect != "postgresql":
        return {"available": False, "items": []}

    # Берём денормализованный центроид (фаза 7.4) — воркер
    # `embed_messages_for_integration` пересчитывает его после батча.
    src_conv = await session.get(Conversation, conversation_id)
    if src_conv is None or not src_conv.embedding_centroid:
        return {"available": True, "items": [], "reason": "no_embeddings"}
    centroid = list(src_conv.embedding_centroid)

    # Сериализуем вектор в строковый литерал pgvector: '[v1,v2,...]'.
    # Так избегаем зависимости от регистрации asyncpg-codec'а в сессии.
    centroid_str = "[" + ",".join(f"{v:.6f}" for v in centroid) + "]"

    # Запрос напрямую по центроидам диалогов — одна строка на диалог,
    # ivfflat-индекс ix_conversations_centroid_cosine ускоряет top-K.
    # Раньше тут был MIN(distance) GROUP BY conversation_id по messages —
    # это давало seq-scan на > 100k сообщений.
    sql = text(
        """
        SELECT c.id AS conv_id,
               c.embedding_centroid <=> CAST(:centroid AS vector) AS distance
          FROM conversations c
          JOIN integrations i ON i.id = c.integration_id
         WHERE i.tenant_id = :tenant_id
           AND c.id <> :conv_id
           AND c.embedding_centroid IS NOT NULL
         ORDER BY distance ASC
         LIMIT :lim
        """
    )
    rows = (
        await session.execute(
            sql,
            {
                "centroid": centroid_str,
                "tenant_id": user.tenant_id,
                "conv_id": conversation_id,
                "lim": limit,
            },
        )
    ).all()
    if not rows:
        return {"available": True, "items": []}

    conv_ids = [r.conv_id for r in rows]
    distances = {r.conv_id: float(r.distance) for r in rows}

    convs = (
        await session.execute(
            select(Conversation).where(Conversation.id.in_(conv_ids))
        )
    ).scalars().all()
    by_id = {c.id: c for c in convs}

    items = []
    for conv_id in conv_ids:
        conv = by_id.get(conv_id)
        if not conv:
            continue
        d = distances[conv_id]
        items.append(
            {
                **ConversationOut.model_validate(conv).model_dump(mode="json"),
                "distance": d,
                # Cosine similarity для удобства фронта: 1 - distance (для
                # нормализованных векторов distance ∈ [0,2], similarity ∈ [-1,1]).
                "similarity": 1.0 - d,
            }
        )
    return {"available": True, "items": items}


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[Message]:
    await _get_owned_conv(session, conversation_id, user)
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.sent_at)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
