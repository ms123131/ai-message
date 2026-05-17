"""REST API для управления подключениями (Bitrix24 и др.)."""

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.db.models import (
    ImportJob,
    ImportJobStatus,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
)
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24 import build_authorize_url, exchange_code
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.events import (
    SUPPORTED_EVENTS,
    bind_events,
    unbind_events,
)
from app.integrations.bitrix24.importer import run_import_job
from app.integrations.bitrix24.oauth import BitrixOAuthError
from app.schemas.integration import (
    Bitrix24OAuthCreate,
    Bitrix24WebhookCreate,
    IntegrationCreated,
    IntegrationOut,
    OAuthExchange,
)


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


def _new_id() -> str:
    return f"b24_{secrets.token_urlsafe(8).lower()}"


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(
    session: AsyncSession = Depends(get_session),
) -> list[Integration]:
    result = await session.execute(
        select(Integration).order_by(Integration.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{integration_id}", response_model=IntegrationOut)
async def get_integration(
    integration_id: str,
    session: AsyncSession = Depends(get_session),
) -> Integration:
    obj = await session.get(Integration, integration_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Integration not found")
    return obj


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    obj = await session.get(Integration, integration_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Integration not found")
    await session.delete(obj)
    await session.commit()


@router.post(
    "/bitrix24/oauth",
    response_model=IntegrationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_bitrix24_oauth(
    body: Bitrix24OAuthCreate,
    session: AsyncSession = Depends(get_session),
) -> IntegrationCreated:
    """
    Создаёт «черновик» OAuth-подключения и возвращает URL авторизации портала.

    Фронтенд должен перенаправить пользователя по `authorize_url`. После успешной
    авторизации портал вернёт пользователя на /integrations/bitrix24/callback
    с параметрами code/state, которые передаются в /oauth/exchange.
    """
    integration = Integration(
        id=_new_id(),
        kind=IntegrationKind.bitrix24,
        mode=IntegrationMode.oauth,
        label=body.label,
        domain=body.domain,
        client_id=body.client_id,
        client_secret=body.client_secret,
        status=IntegrationStatus.pending,
    )
    session.add(integration)
    await session.commit()
    await session.refresh(integration)

    state = f"{integration.id}.{secrets.token_urlsafe(8)}"
    authorize_url = build_authorize_url(
        domain=body.domain,
        client_id=body.client_id,
        state=state,
    )
    return IntegrationCreated(
        integration=IntegrationOut.model_validate(integration),
        authorize_url=authorize_url,
    )


@router.post(
    "/bitrix24/webhook",
    response_model=IntegrationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_bitrix24_webhook(
    body: Bitrix24WebhookCreate,
    session: AsyncSession = Depends(get_session),
) -> Integration:
    url = str(body.webhook_url).rstrip("/") + "/"
    try:
        domain = url.split("//", 1)[1].split("/", 1)[0]
    except IndexError:
        raise HTTPException(status_code=400, detail="Cannot extract domain from webhook URL")

    integration = Integration(
        id=_new_id(),
        kind=IntegrationKind.bitrix24,
        mode=IntegrationMode.webhook,
        label=body.label,
        domain=domain,
        webhook_url=url,
        status=IntegrationStatus.connected,
    )
    session.add(integration)
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
) -> dict:
    """
    Регистрирует обработчик событий Open Channels через `event.bind`.

    Дёргается вручную после того, как `WEBHOOK_BASE_URL` указывает на доступный
    извне адрес (production или ngrok). Возвращает результат каждого вызова.
    """
    integration = await session.get(Integration, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    handler = _handler_url()
    async with BitrixClient(integration, session) as client:
        results = await bind_events(client, handler)
    await session.commit()
    return {"handler": handler, "events": SUPPORTED_EVENTS, "results": results}


async def _run_import_background(integration_id: str, job_id: str) -> None:
    """Запускает импорт в своей сессии БД — не зависим от request-сессии."""
    async with AsyncSessionLocal() as session:
        job = await session.get(ImportJob, job_id)
        integration = await session.get(Integration, integration_id)
        if not job or not integration:
            return
        async with BitrixClient(integration, session) as client:
            await run_import_job(client, session, job, integration)


@router.post(
    "/{integration_id}/import",
    response_model=ImportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_import(
    integration_id: str,
    background: BackgroundTasks,
    days: int = Query(30, ge=1, le=180),
    session: AsyncSession = Depends(get_session),
) -> ImportJob:
    integration = await session.get(Integration, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    job = ImportJob(
        id=f"imp_{secrets.token_urlsafe(8).lower()}",
        integration_id=integration.id,
        days=days,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    background.add_task(_run_import_background, integration.id, job.id)
    return job


@router.get("/{integration_id}/import-jobs", response_model=list[ImportJobOut])
async def list_import_jobs(
    integration_id: str,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[ImportJob]:
    result = await session.execute(
        select(ImportJob)
        .where(ImportJob.integration_id == integration_id)
        .order_by(desc(ImportJob.created_at))
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/{integration_id}/events/unsubscribe")
async def unsubscribe_events(
    integration_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict:
    integration = await session.get(Integration, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    handler = _handler_url()
    async with BitrixClient(integration, session) as client:
        results = await unbind_events(client, handler)
    await session.commit()
    return {"handler": handler, "events": SUPPORTED_EVENTS, "results": results}


@router.post(
    "/bitrix24/oauth/exchange",
    response_model=IntegrationOut,
)
async def exchange_oauth_code(
    body: OAuthExchange,
    session: AsyncSession = Depends(get_session),
) -> Integration:
    """
    Обменивает первый авторизационный код на access/refresh токены.
    Вызывается фронтендом после callback'а от Bitrix24.
    """
    integration = await session.get(Integration, body.integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if integration.mode != IntegrationMode.oauth:
        raise HTTPException(status_code=400, detail="Not an OAuth integration")
    if not integration.client_id or not integration.client_secret:
        raise HTTPException(status_code=400, detail="Missing client_id/client_secret")

    try:
        tokens = await exchange_code(
            client_id=integration.client_id,
            client_secret=integration.client_secret,
            code=body.code,
        )
    except BitrixOAuthError as exc:
        integration.status = IntegrationStatus.error
        await session.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    integration.access_token = tokens.access_token
    integration.refresh_token = tokens.refresh_token
    integration.member_id = tokens.member_id or body.member_id
    integration.scope = tokens.scope or body.scope
    integration.domain = tokens.domain or body.domain or integration.domain
    integration.expires_at = datetime.now(UTC) + timedelta(
        seconds=tokens.expires_in
    )
    integration.status = IntegrationStatus.connected

    await session.commit()
    await session.refresh(integration)
    return integration
