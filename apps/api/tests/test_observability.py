"""Тесты структурированного логирования + X-Request-Id middleware."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_response_has_request_id_header(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    rid = resp.headers.get("X-Request-Id")
    assert rid and len(rid) >= 8


@pytest.mark.asyncio
async def test_inbound_request_id_is_preserved(client):
    """Если шлюз/фронт прислал X-Request-Id — пробрасываем в ответ как есть.
    Это даёт сквозную трассировку через несколько сервисов."""
    resp = await client.get(
        "/api/v1/health", headers={"X-Request-Id": "client-trace-abc-123"}
    )
    assert resp.status_code == 200
    assert resp.headers["X-Request-Id"] == "client-trace-abc-123"


@pytest.mark.asyncio
async def test_request_id_varies_between_requests(client):
    a = await client.get("/api/v1/health")
    b = await client.get("/api/v1/health")
    assert a.headers["X-Request-Id"] != b.headers["X-Request-Id"]


def test_setup_logging_idempotent():
    """setup_logging() можно вызывать несколько раз без побочных эффектов.
    Это важно для тестов и для перезагрузки uvicorn dev-mode."""
    from app.observability.logging import setup_logging

    setup_logging(json_logs=True)
    setup_logging(json_logs=False)
    setup_logging(json_logs=True)
