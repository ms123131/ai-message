"""AI-ассистент «спроси свою переписку» (planApp.md B10, v1).

Чат поверх диалогов tenant'а: tenant-safe RAG (см. services/ai_assistant) +
smart-LLM. Ответы со ссылками на диалоги-источники, multi-turn в рамках треда,
учёт бизнес-профиля. Без стриминга и tool-use (это v2).

Если smart-LLM не настроен (llm_smart_provider=null) — /ai/chat отвечает 503.
Если нет pgvector/эмбеддингов — отвечаем, но честно помечаем degraded-режим.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db import get_session
from app.db.models import AiMessage, AiMessageRole, AiThread, Tenant
from app.db.models import User as UserModel
from app.integrations.llm.base import LLMError, LLMMessage
from app.integrations.llm.factory import get_llm
from app.services.ai_assistant.analytics import (
    compute_weak_spots,
    looks_like_weak_spot_query,
)
from app.services.ai_assistant.prompt import build_messages, build_system_prompt
from app.services.ai_assistant.retrieval import retrieve_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-assistant"])

_MAX_QUESTION_LEN = 4000
_ANSWER_MAX_TOKENS = 1024


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(8).lower()}"


def _smart_enabled() -> bool:
    return get_settings().llm_smart_provider != "null"


# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------


class SourceOut(BaseModel):
    conversation_id: str
    title: str
    similarity: float


class ChatRequest(BaseModel):
    thread_id: str | None = None
    message: str = Field(min_length=1, max_length=_MAX_QUESTION_LEN)


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    sources: list[SourceOut]
    degraded: bool = False


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    created_at: object
    updated_at: object


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    role: AiMessageRole
    content: str
    sources: list[SourceOut] | None = None
    created_at: object


class ThreadDetailOut(BaseModel):
    id: str
    title: str
    messages: list[MessageOut]


class BusinessProfileOut(BaseModel):
    business_profile: str | None = None


class BusinessProfilePut(BaseModel):
    business_profile: str | None = Field(default=None, max_length=8000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_thread(
    session: AsyncSession, thread_id: str, user: UserModel
) -> AiThread:
    thread = await session.get(AiThread, thread_id)
    if thread is None or thread.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> ChatResponse:
    if not _smart_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI-ассистент недоступен: smart-LLM не настроен",
        )

    question = body.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Пустой вопрос")

    # Тред: существующий (с проверкой владения) или новый.
    if body.thread_id:
        thread = await _get_owned_thread(session, body.thread_id, user)
    else:
        thread = AiThread(
            id=_new_id("ait"),
            tenant_id=user.tenant_id,
            user_id=user.id,
            title=question[:120],
        )
        session.add(thread)
        await session.flush()

    # История треда → LLMMessage (до сохранения текущего вопроса).
    history_rows = (
        await session.execute(
            select(AiMessage)
            .where(AiMessage.thread_id == thread.id)
            .order_by(AiMessage.created_at)
        )
    ).scalars().all()
    history = [
        LLMMessage(role=m.role.value, content=m.content) for m in history_rows
    ]

    # Сохраняем вопрос пользователя.
    session.add(
        AiMessage(
            id=_new_id("aim"),
            thread_id=thread.id,
            role=AiMessageRole.user,
            content=question,
        )
    )

    # Retrieval + опц. агрегат слабых мест.
    retrieval = await retrieve_context(session, user.tenant_id, question)
    weak_spots = None
    if looks_like_weak_spot_query(question):
        weak_spots = await compute_weak_spots(session, user.tenant_id)

    tenant = await session.get(Tenant, user.tenant_id)
    system_prompt = build_system_prompt(
        business_profile=tenant.ai_business_profile if tenant else None,
        items=retrieval.items,
        weak_spots=weak_spots,
    )
    messages = build_messages(
        system_prompt=system_prompt, history=history, question=question
    )

    llm = get_llm("smart")
    try:
        resp = await llm.chat(
            messages, max_tokens=_ANSWER_MAX_TOKENS, temperature=0.2
        )
    except LLMError as exc:
        logger.warning("ai-assistant LLM error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM временно недоступен, попробуйте ещё раз",
        ) from exc

    sources = [
        SourceOut(
            conversation_id=it.conversation_id,
            title=it.title,
            similarity=round(it.similarity, 4),
        )
        for it in retrieval.items
    ]

    session.add(
        AiMessage(
            id=_new_id("aim"),
            thread_id=thread.id,
            role=AiMessageRole.assistant,
            content=resp.content,
            sources=[s.model_dump() for s in sources],
            model=resp.model,
            tokens_in=resp.input_tokens,
            tokens_out=resp.output_tokens,
        )
    )
    # Бамп updated_at треда для сортировки списка.
    thread.title = thread.title or question[:120]
    await session.commit()

    return ChatResponse(
        thread_id=thread.id,
        answer=resp.content,
        sources=sources,
        degraded=not retrieval.available,
    )


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[AiThread]:
    rows = (
        await session.execute(
            select(AiThread)
            .where(AiThread.tenant_id == user.tenant_id)
            .order_by(AiThread.updated_at.desc())
            .limit(100)
        )
    ).scalars().all()
    return list(rows)


@router.get("/threads/{thread_id}", response_model=ThreadDetailOut)
async def get_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> ThreadDetailOut:
    thread = await _get_owned_thread(session, thread_id, user)
    rows = (
        await session.execute(
            select(AiMessage)
            .where(AiMessage.thread_id == thread.id)
            .order_by(AiMessage.created_at)
        )
    ).scalars().all()
    return ThreadDetailOut(
        id=thread.id,
        title=thread.title,
        messages=[MessageOut.model_validate(m) for m in rows],
    )


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> None:
    thread = await _get_owned_thread(session, thread_id, user)
    await session.execute(delete(AiThread).where(AiThread.id == thread.id))
    await session.commit()


@router.get("/business-profile", response_model=BusinessProfileOut)
async def get_business_profile(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> BusinessProfileOut:
    tenant = await session.get(Tenant, user.tenant_id)
    return BusinessProfileOut(
        business_profile=tenant.ai_business_profile if tenant else None
    )


@router.put("/business-profile", response_model=BusinessProfileOut)
async def put_business_profile(
    body: BusinessProfilePut,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> BusinessProfileOut:
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    value = (body.business_profile or "").strip() or None
    tenant.ai_business_profile = value
    await session.commit()
    return BusinessProfileOut(business_profile=value)
