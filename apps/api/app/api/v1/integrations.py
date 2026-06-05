"""REST API для управления подключениями Bitrix24."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db import get_session
from app.db.models import (
    ImportJob,
    ImportJobStatus,
    Integration,
    IntegrationStatus,
)
from app.db.models import User as UserModel
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.events import (
    SUPPORTED_EVENTS,
    bind_events,
    unbind_events,
)
from app.schemas.integration import (
    Bitrix24ConnectNotInstalled,
    Bitrix24ConnectRequest,
    IntegrationOut,
)
from app.security.audit import write_audit
from app.security.ratelimit import limiter


class ImportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    integration_id: str
    status: ImportJobStatus
    days: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    processed_sessions: int
    processed_messages: int
    error: str | None = None
    created_at: datetime


router = APIRouter(prefix="/integrations", tags=["integrations"])


def _normalize_domain(raw: str) -> str:
    """`https://b24-xyz.bitrix24.ru/` → `b24-xyz.bitrix24.ru` (без схемы и пути)."""
    s = raw.strip().lower()
    if s.startswith("http://"):
        s = s[len("http://") :]
    elif s.startswith("https://"):
        s = s[len("https://") :]
    s = s.split("/", 1)[0]
    return s.rstrip(".")


def _install_url() -> str:
    settings = get_settings()
    base = (settings.webhook_base_url or "").rstrip("/")
    if not base:
        return "/install/bitrix24"
    return f"{base}/install/bitrix24"


async def _get_owned(
    session: AsyncSession, integration_id: str, user: UserModel
) -> Integration:
    obj = await session.get(Integration, integration_id)
    if not obj or obj.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Integration not found")
    return obj


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[Integration]:
    result = await session.execute(
        select(Integration)
        .where(Integration.tenant_id == user.tenant_id)
        .order_by(Integration.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{integration_id}", response_model=IntegrationOut)
async def get_integration(
    integration_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> Integration:
    return await _get_owned(session, integration_id, user)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> None:
    obj = await _get_owned(session, integration_id, user)
    await write_audit(
        session,
        action="integration.delete",
        tenant_id=user.tenant_id,
        user_id=user.id,
        target_type="integration",
        target_id=obj.id,
        request=request,
        meta={"domain": obj.domain, "kind": obj.kind.value if obj.kind else None},
    )
    await session.delete(obj)
    await session.commit()


@router.get("/bitrix24/config")
async def bitrix24_config() -> dict[str, Any]:
    """Сообщает фронту, сконфигурировано ли глобальное приложение в .env.

    Если `has_global_credentials=true`, UI может не требовать ввода
    client_id/secret — сервер подставит их из BITRIX24_APP_CLIENT_ID/SECRET.
    """
    settings = get_settings()
    return {
        "has_global_credentials": bool(
            settings.bitrix24_app_client_id and settings.bitrix24_app_client_secret
        ),
        "install_url": _install_url(),
    }


@router.post(
    "/bitrix24/connect",
    response_model=IntegrationOut,
    responses={404: {"model": Bitrix24ConnectNotInstalled}},
)
async def connect_bitrix24(
    body: Bitrix24ConnectRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> Integration:
    """
    Подключение Bitrix24-портала по доменному имени.

    Сценарий:
    1. Клиент устанавливает наше тиражное приложение на свой портал;
       при установке Bitrix24 шлёт токены в `/install/bitrix24`,
       мы их сохраняем в Integration (без tenant_id — pending).
    2. Клиент возвращается в наш UI и сообщает доменное имя портала.
       Этот endpoint ищет Integration по домену и закрепляет за tenant'ом.

    Если интеграции нет — возвращаем 404 с инструкцией поставить приложение.
    """
    import secrets

    from app.db.models import IntegrationKind, IntegrationMode

    domain = _normalize_domain(body.domain)
    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")

    # client_id и client_secret должны идти парой.
    if bool(body.client_id) != bool(body.client_secret):
        raise HTTPException(
            status_code=400,
            detail="client_id и client_secret должны быть указаны вместе",
        )

    # Если в body нет credentials — пробуем глобальные из .env
    # (BITRIX24_APP_CLIENT_ID/SECRET). Это позволяет «одним приложением
    # на всех клиентов» работать в режиме локального приложения:
    # клиент только вводит домен, а секреты подставляются из конфига.
    effective_client_id = body.client_id
    effective_client_secret = body.client_secret
    if not effective_client_id and not effective_client_secret:
        settings = get_settings()
        if settings.bitrix24_app_client_id and settings.bitrix24_app_client_secret:
            effective_client_id = settings.bitrix24_app_client_id
            effective_client_secret = settings.bitrix24_app_client_secret

    is_local_app = bool(effective_client_id and effective_client_secret)

    integration = (
        await session.execute(
            select(Integration).where(Integration.domain == domain).limit(1)
        )
    ).scalar_one_or_none()

    if integration and integration.tenant_id and integration.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=409,
            detail="Этот портал уже подключён к другому рабочему пространству",
        )

    if not integration:
        if not is_local_app:
            # Marketplace-сценарий: ждём, пока клиент поставит наше тиражное
            # приложение — без этого мы не получим токены.
            raise HTTPException(
                status_code=404,
                detail={
                    "status": "not_installed",
                    "domain": domain,
                    "install_instructions_url": _install_url(),
                    "message": (
                        "Приложение ai-message не установлено на этом портале. "
                        "Установите его из Bitrix24 Marketplace, затем повторите подключение."
                    ),
                },
            )
        # Local-сценарий: создаём заготовку с client_id/secret и сразу
        # привязываем к tenant'у. Токены прилетят в install-handler, когда
        # клиент создаст/переустановит локальное приложение на портале.
        integration = Integration(
            id=f"b24_{secrets.token_urlsafe(8).lower()}",
            tenant_id=user.tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label=body.label or domain,
            domain=domain,
            status=IntegrationStatus.pending,
            client_id=effective_client_id,
            client_secret=effective_client_secret,
        )
        session.add(integration)
    else:
        integration.tenant_id = user.tenant_id
        if body.label:
            integration.label = body.label
        if is_local_app:
            integration.client_id = effective_client_id
            integration.client_secret = effective_client_secret
        # status: connected если уже есть токены, иначе pending.
        if integration.access_token and integration.refresh_token:
            integration.status = IntegrationStatus.connected
        else:
            integration.status = IntegrationStatus.pending

    await write_audit(
        session,
        action="integration.connect",
        tenant_id=user.tenant_id,
        user_id=user.id,
        target_type="integration",
        target_id=integration.id,
        request=request,
        meta={"domain": domain, "is_local_app": is_local_app},
    )
    await session.commit()
    await session.refresh(integration)
    return integration


def _handler_url() -> str:
    settings = get_settings()
    base = (settings.webhook_base_url or "").rstrip("/")
    if not base:
        raise HTTPException(
            status_code=400,
            detail="WEBHOOK_BASE_URL not configured — задайте публичный URL в .env",
        )
    return f"{base}/webhooks/bitrix24"


@router.post("/{integration_id}/events/subscribe")
async def subscribe_events(
    integration_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict:
    integration = await _get_owned(session, integration_id, user)
    handler = _handler_url()
    async with BitrixClient(integration, session) as client:
        try:
            app_info: Any = await client.call("app.info")
        except Exception as exc:  # noqa: BLE001
            app_info = {"error": str(exc)}
        results = await bind_events(client, handler)
    await session.commit()
    return {
        "handler": handler,
        "events": SUPPORTED_EVENTS,
        "app_info": app_info,
        "results": results,
    }


@router.post("/{integration_id}/events/unsubscribe")
async def unsubscribe_events(
    integration_id: str,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict:
    integration = await _get_owned(session, integration_id, user)
    handler = _handler_url()
    async with BitrixClient(integration, session) as client:
        results = await unbind_events(client, handler)
    await session.commit()
    return {"handler": handler, "events": SUPPORTED_EVENTS, "results": results}


@router.post(
    "/{integration_id}/import",
    response_model=ImportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("6/minute")
async def trigger_import(
    request: Request,  # noqa: ARG001 — нужен slowapi для key_func
    integration_id: str,
    days: int = Query(30, ge=1, le=180),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> ImportJob:
    """Создаёт ImportJob (pending) и ставит задачу в arq-очередь.

    Реально импорт делает воркер (см. `app/workers/tasks/bitrix_import.py`).
    Эндпоинт возвращает 202 + job сразу, без блокировки HTTP-обработчика.
    """
    import secrets

    from app.workers.redis_pool import get_pool

    integration = await _get_owned(session, integration_id, user)
    job = ImportJob(
        id=f"imp_{secrets.token_urlsafe(8).lower()}",
        integration_id=integration.id,
        days=days,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    pool = await get_pool()
    await pool.enqueue_job("run_import_job_task", integration.id, job.id)
    return job


@router.post(
    "/{integration_id}/analyze-sentiment",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("6/minute")
async def trigger_sentiment_analysis(
    request: Request,  # noqa: ARG001 — нужен slowapi
    integration_id: str,
    batch_size: int = Query(200, ge=10, le=1000),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """Запускает батч-анализ тональности для интеграции (один проход).

    Воркер берёт до `batch_size` необработанных сообщений (sentiment IS NULL)
    и классифицирует их через fast-LLM. Если необработанных больше — нужно
    дёрнуть ещё раз. Это сознательно: не хотим, чтобы одна интеграция
    блокировала очередь надолго при первом импорте за полгода истории.
    """
    from app.workers.redis_pool import get_pool

    integration = await _get_owned(session, integration_id, user)

    pool = await get_pool()
    job = await pool.enqueue_job(
        "analyze_sentiment_for_integration",
        integration.id,
        batch_size,
    )
    return {
        "status": "accepted",
        "job_id": getattr(job, "job_id", "unknown"),
        "integration_id": integration.id,
    }


@router.post(
    "/{integration_id}/analyze-tags",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("6/minute")
async def trigger_tags_analysis(
    request: Request,  # noqa: ARG001 — нужен slowapi
    integration_id: str,
    batch_size: int = Query(200, ge=10, le=1000),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """Запускает батч авто-тегирования сообщений по словарю (фаза 6.2).

    Один проход на до `batch_size` сообщений. Архитектура та же, что у
    sentiment-эндпоинта; теги и sentiment могут выполняться параллельно
    (разные локи) и не мешают друг другу.
    """
    from app.workers.redis_pool import get_pool

    integration = await _get_owned(session, integration_id, user)
    pool = await get_pool()
    job = await pool.enqueue_job(
        "analyze_tags_for_integration",
        integration.id,
        batch_size,
    )
    return {
        "status": "accepted",
        "job_id": getattr(job, "job_id", "unknown"),
        "integration_id": integration.id,
    }


@router.post(
    "/{integration_id}/analyze-entities",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("6/minute")
async def trigger_entities_analysis(
    request: Request,  # noqa: ARG001 — нужен slowapi
    integration_id: str,
    batch_size: int = Query(500, ge=10, le=2000),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """Извлечение сущностей (телефон, email, URL, трек, сумма, NER) — фаза 6.6.

    Работает локально через Natasha + регулярки, без LLM-вызовов. Можно
    запускать одновременно с sentiment/tags — разные локи.
    """
    from app.workers.redis_pool import get_pool

    integration = await _get_owned(session, integration_id, user)
    pool = await get_pool()
    job = await pool.enqueue_job(
        "analyze_entities_for_integration",
        integration.id,
        batch_size,
    )
    return {
        "status": "accepted",
        "job_id": getattr(job, "job_id", "unknown"),
        "integration_id": integration.id,
    }


@router.post(
    "/{integration_id}/analyze-embeddings",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("6/minute")
async def trigger_embeddings_analysis(
    request: Request,  # noqa: ARG001 — нужен slowapi
    integration_id: str,
    batch_size: int = Query(200, ge=10, le=1000),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """Расчёт эмбеддингов сообщений (фаза 6.5).

    Локальная модель sentence-transformers на CPU, без LLM-вызовов.
    Заполняет `messages.embedding` (pgvector) — основа для семантического
    поиска похожих диалогов в `GET /conversations/{id}/similar`.
    """
    from app.workers.redis_pool import get_pool

    integration = await _get_owned(session, integration_id, user)
    pool = await get_pool()
    job = await pool.enqueue_job(
        "embed_messages_for_integration",
        integration.id,
        batch_size,
    )
    return {
        "status": "accepted",
        "job_id": getattr(job, "job_id", "unknown"),
        "integration_id": integration.id,
    }


@router.post(
    "/{integration_id}/enrich-conversations",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("3/minute")
async def trigger_enrich_conversations(
    request: Request,  # noqa: ARG001 — нужен slowapi
    integration_id: str,
    limit: int = Query(500, ge=1, le=2000),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    """Бэкфил: ставит enrich-задачу на каждый известный диалог интеграции.

    Используется, когда диалоги пришли через webhook и у них нет CRM-привязок:
    дашборд показывает «Со сделкой 0», хотя в Bitrix24 сделки есть. После
    переподключения OAuth/первого OAuth — дёрнуть один раз.
    """
    from app.db.models import Conversation
    from app.workers.redis_pool import get_pool

    integration = await _get_owned(session, integration_id, user)
    rows = (
        await session.execute(
            select(Conversation.external_id)
            .where(Conversation.integration_id == integration.id)
            .order_by(desc(Conversation.created_at))
            .limit(limit)
        )
    ).all()
    chat_ids = [r[0] for r in rows if r[0]]

    pool = await get_pool()
    for chat_id in chat_ids:
        await pool.enqueue_job(
            "enrich_conversation_from_chat", integration.id, chat_id
        )
    return {
        "status": "accepted",
        "integration_id": integration.id,
        "enqueued": len(chat_ids),
    }


@router.get("/{integration_id}/import-jobs", response_model=list[ImportJobOut])
async def list_import_jobs(
    integration_id: str,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> list[ImportJob]:
    await _get_owned(session, integration_id, user)
    result = await session.execute(
        select(ImportJob)
        .where(ImportJob.integration_id == integration_id)
        .order_by(desc(ImportJob.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())
