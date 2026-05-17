"""REST API для управления подключениями Bitrix24."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
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
from app.db.session import AsyncSessionLocal
from app.integrations.bitrix24.client import BitrixClient
from app.integrations.bitrix24.events import (
    SUPPORTED_EVENTS,
    bind_events,
    unbind_events,
)
from app.integrations.bitrix24.importer import run_import_job
from app.schemas.integration import (
    Bitrix24ConnectNotInstalled,
    Bitrix24ConnectRequest,
    IntegrationOut,
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
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(get_current_user),
) -> None:
    obj = await _get_owned(session, integration_id, user)
    await session.delete(obj)
    await session.commit()


@router.post(
    "/bitrix24/connect",
    response_model=IntegrationOut,
    responses={404: {"model": Bitrix24ConnectNotInstalled}},
)
async def connect_bitrix24(
    body: Bitrix24ConnectRequest,
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
    domain = _normalize_domain(body.domain)
    if not domain:
        raise HTTPException(status_code=400, detail="Domain is required")

    integration = (
        await session.execute(
            select(Integration).where(Integration.domain == domain).limit(1)
        )
    ).scalar_one_or_none()

    if not integration:
        # Хочется 404 с тегом not_installed, а не «не найдено».
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

    if integration.tenant_id and integration.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=409,
            detail="Этот портал уже подключён к другому рабочему пространству",
        )

    integration.tenant_id = user.tenant_id
    if body.label:
        integration.label = body.label
    integration.status = IntegrationStatus.connected
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


async def _run_import_background(integration_id: str, job_id: str) -> None:
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
    user: UserModel = Depends(get_current_user),
) -> ImportJob:
    import secrets

    integration = await _get_owned(session, integration_id, user)
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
