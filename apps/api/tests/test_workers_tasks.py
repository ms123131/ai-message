"""Тесты задач воркера: поллинг + импорт-джоб через arq-протокол."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy import select

from app.db.models import (
    Conversation,
    ImportJob,
    ImportJobStatus,
    Integration,
    IntegrationKind,
    IntegrationMode,
    IntegrationStatus,
)
from app.db.session import AsyncSessionLocal
from app.workers.tasks.bitrix_import import run_import_job_task
from app.workers.tasks.bitrix_poll import poll_integration


class _FakeClient:
    """Подмена BitrixClient — возвращает один диалог и пустые крон-методы."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN001
        return None

    async def call(self, method, params=None):
        self.calls.append((method, params))
        if method == "im.recent.get":
            return [
                {
                    "chat_id": 4242,
                    "date_last_activity": datetime.now(UTC).isoformat(),
                }
            ]
        if method == "imopenlines.session.history.get":
            return {
                "chatId": 4242,
                "session": {"STATUS": 80},
                "message": {
                    "1": {
                        "id": "1",
                        "senderid": "200",
                        "date": datetime.now(UTC).isoformat(),
                        "text": "hi",
                    }
                },
                "users": {"200": {"id": "200", "name": "C", "connector": True}},
                "chat": {"4242": {"id": "4242", "entityId": "livechat|1|1|200"}},
            }
        # Все остальные методы (crm.*, user.get) — пусто.
        return []


@pytest.fixture
def patch_bitrix_client(monkeypatch):
    """Подменяет BitrixClient в обоих модулях, где он используется задачами."""
    fake = _FakeClient()

    def _factory(*_args, **_kwargs):
        return fake

    monkeypatch.setattr(
        "app.workers.tasks.bitrix_poll.BitrixClient", _factory
    )
    monkeypatch.setattr(
        "app.workers.tasks.bitrix_import.BitrixClient", _factory
    )
    return fake


async def _make_integration(tenant_id: str | None = None) -> str:
    async with AsyncSessionLocal() as session:
        integration = Integration(
            id="intg_worker",
            tenant_id=tenant_id,
            kind=IntegrationKind.bitrix24,
            mode=IntegrationMode.oauth,
            label="W",
            domain="w.bitrix24.ru",
            status=IntegrationStatus.connected,
            access_token="a",
            refresh_token="r",
            # expires в будущем — клиент не пойдёт за refresh.
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(integration)
        await session.commit()
        return integration.id


@pytest.mark.asyncio
async def test_poll_integration_runs_import_under_lock(
    client, patch_bitrix_client  # noqa: ARG001
):
    integration_id = await _make_integration()
    redis = FakeRedis()
    try:
        ctx = {"redis": redis}
        result = await poll_integration(ctx, integration_id)
    finally:
        await redis.aclose()

    assert result["sessions"] == 1
    assert result["messages"] == 1
    assert result["skipped"] == 0

    # Диалог реально создался — задача дошла до import_open_lines.
    async with AsyncSessionLocal() as session:
        convs = (await session.execute(select(Conversation))).scalars().all()
        assert len(convs) == 1


@pytest.mark.asyncio
async def test_poll_integration_skips_when_lock_held(
    client, patch_bitrix_client  # noqa: ARG001
):
    integration_id = await _make_integration()
    redis = FakeRedis()
    try:
        # Заранее взяли лок — задача должна корректно пропустить проход.
        from app.workers.locks import lock_key

        await redis.set(lock_key(integration_id), "other-worker", nx=True, ex=60)

        ctx = {"redis": redis}
        result = await poll_integration(ctx, integration_id)
        assert result["skipped"] == 1
        assert result["sessions"] == 0
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_run_import_job_task_marks_done(
    client, patch_bitrix_client  # noqa: ARG001
):
    integration_id = await _make_integration()
    async with AsyncSessionLocal() as session:
        job = ImportJob(id="imp_x", integration_id=integration_id, days=30)
        session.add(job)
        await session.commit()
        job_id = job.id

    redis = FakeRedis()
    try:
        ctx = {"redis": redis}
        status = await run_import_job_task(ctx, integration_id, job_id)
    finally:
        await redis.aclose()

    assert status == "done"

    async with AsyncSessionLocal() as session:
        job = await session.get(ImportJob, job_id)
        assert job.status == ImportJobStatus.done
        assert job.error is None


@pytest.mark.asyncio
async def test_run_import_job_task_fails_gracefully_when_locked(
    client, patch_bitrix_client  # noqa: ARG001
):
    integration_id = await _make_integration()
    async with AsyncSessionLocal() as session:
        job = ImportJob(id="imp_y", integration_id=integration_id, days=30)
        session.add(job)
        await session.commit()
        job_id = job.id

    redis = FakeRedis()
    try:
        # Лок занят — задача должна пометить job как failed с понятной ошибкой.
        from app.workers.locks import lock_key

        await redis.set(lock_key(integration_id), "other", nx=True, ex=60)

        ctx = {"redis": redis}
        status = await run_import_job_task(ctx, integration_id, job_id)
    finally:
        await redis.aclose()

    assert status == "locked"
    async with AsyncSessionLocal() as session:
        job = await session.get(ImportJob, job_id)
        assert job.status == ImportJobStatus.failed
        assert "занят" in (job.error or "")
