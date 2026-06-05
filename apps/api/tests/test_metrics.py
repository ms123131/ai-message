"""Тесты Prometheus-метрик."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Стандартные HTTP-метрики от instrumentator'а
    assert "http_request_duration_seconds" in body
    # Кастомные семейства, объявленные в app.observability.metrics
    assert "nlp_pending_messages" in body
    assert "llm_request_seconds" in body
    # Гистограммы должны иметь HELP/TYPE
    assert "# HELP llm_request_seconds" in body
    assert "# TYPE llm_request_seconds histogram" in body


@pytest.mark.asyncio
async def test_metrics_reflect_http_traffic(client):
    # Прогреем счётчик пачкой запросов и убедимся, что они отразились
    for _ in range(3):
        await client.get("/api/v1/health")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Хоть один сэмпл с path /api/v1/health должен попасть в метрику
    assert "/api/v1/health" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_excluded_from_self(client):
    # Скрап /metrics не должен учитывать сам себя как HTTP-вызов
    # (иначе размер вывода будет расти при каждом скрапе).
    await client.get("/metrics")
    await client.get("/metrics")
    resp = await client.get("/metrics")
    # Проверяем, что /metrics НЕ упомянут как handler в http_request_total
    # (excluded_handlers исключает /metrics из инструментирования).
    lines = [
        l for l in resp.text.splitlines()
        if l.startswith("http_requests_total") and "/metrics" in l
    ]
    assert lines == []
