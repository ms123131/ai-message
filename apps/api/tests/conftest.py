import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")


class _FakeArqPool:
    """Заглушка arq-пула для тестов: ничего не отправляет в Redis, просто
    записывает вызовы. Эндпоинты вроде /integrations/{id}/import используют
    `get_pool().enqueue_job(...)`, и без подмены этот вызов попытался бы
    подключиться к настоящему Redis. В тестах нам достаточно проверить,
    что job создан в БД — реальная очередь задач покрывается отдельно
    через test_workers_tasks.
    """

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple, dict]] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.enqueued.append((name, args, kwargs))
        return type("FakeJob", (), {"job_id": "fake-job-id"})()

    async def aclose(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _stub_arq_pool(monkeypatch):
    """Авто-подмена: все тесты получают fake arq-пул без обращения к Redis."""
    pool = _FakeArqPool()

    async def _get_pool():
        return pool

    monkeypatch.setattr("app.workers.redis_pool.get_pool", _get_pool)
    # close_pool читает глобальный `_pool`; в тестах он остаётся None
    # (мы возвращаем fake, не сохраняя его в модуль), поэтому реальный
    # close_pool становится no-op — патчить его не нужно.
    return pool


@pytest.fixture
async def client():
    """
    HTTP-клиент с уже зарегистрированным тестовым пользователем —
    каждый запрос автоматически идёт под bearer-токеном этого юзера.
    Это удобно: подавляющее большинство тестов работают с защищёнными
    эндпойнтами в контексте одного tenant'а.
    """
    from httpx import ASGITransport, AsyncClient

    from app.db.session import Base, engine
    from app.main import app

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Регистрируем дефолтного пользователя для всех тестов.
        resp = await ac.post(
            "/api/v1/auth/register",
            json={
                "email": "tester@example.com",
                "password": "test-password-123",
                "workspace_name": "Test WS",
            },
        )
        assert resp.status_code == 201, resp.text
        token = resp.json()["access_token"]
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac


@pytest.fixture
def auth_tenant_id(client):  # noqa: ARG001 — нужна последовательность фикстур
    """tenant_id из дефолтного пользователя — для сидинга в БД напрямую."""
    import jwt

    from app.config import get_settings

    settings = get_settings()
    token = client.headers["Authorization"].split(" ", 1)[1]
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return payload["tid"]
