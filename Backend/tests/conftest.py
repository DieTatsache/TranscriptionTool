import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import undefer

import sonora.models  # noqa: F401  (registers tables)
from sonora.config import Settings
from sonora.container import Services, build_services
from sonora.db import Base
from sonora.main import create_app
from sonora.models import TrainingSession, User
from sonora.worker.runner import Worker
from tests.fakes import WEBM_AUDIO, FakeLLM, FakeTranscriber

BASE_URL = "https://testserver"
PASSWORD = "violet-harbor-lantern-42"


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # A developer's shell or .env must never change what the tests exercise.
    for name in list(os.environ):
        if name.startswith("SONORA_"):
            monkeypatch.delenv(name)


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
        "storage_dir": tmp_path / "storage",
        "allowed_hosts": ["testserver"],
        "allowed_origins": ["https://app.example"],
        "argon2_time_cost": 1,
        "argon2_memory_cost_kib": 8,
        "argon2_parallelism": 1,
        "worker_embedded": False,
        "max_upload_mb": 1,
        "transcription_backend": "fake",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def settings_overrides() -> dict[str, Any]:
    """Override per test module/function to tweak settings."""
    return {}


@pytest.fixture
def settings(tmp_path: Path, settings_overrides: dict[str, Any]) -> Settings:
    return make_settings(tmp_path, **settings_overrides)


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def transcriber() -> FakeTranscriber:
    return FakeTranscriber()


@pytest.fixture
async def services(
    settings: Settings, llm: FakeLLM, transcriber: FakeTranscriber
) -> AsyncIterator[Services]:
    services = build_services(settings, llm=llm, transcriber=transcriber)
    async with services.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield services
    await services.aclose()


@pytest.fixture
def app(settings: Settings, services: Services) -> FastAPI:
    return create_app(settings, services=services)


@pytest.fixture
def client_factory(app: FastAPI) -> Callable[[], httpx.AsyncClient]:
    """New client with its own cookie jar (= a different browser)."""

    def make() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)

    return make


@pytest.fixture
async def client(
    client_factory: Callable[[], httpx.AsyncClient],
) -> AsyncIterator[httpx.AsyncClient]:
    async with client_factory() as c:
        yield c


@dataclass
class Account:
    client: httpx.AsyncClient
    email: str
    password: str
    csrf: str
    user_id: str


async def register(
    client: httpx.AsyncClient,
    *,
    email: str = "trainer@example.com",
    name: str = "Test Trainer",
    password: str = PASSWORD,
) -> Account:
    response = await client.post(
        "/api/v1/auth/register", json={"name": name, "email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    client.headers["X-CSRF-Token"] = body["csrf_token"]
    return Account(client, email, password, body["csrf_token"], body["user"]["id"])


@pytest.fixture
async def account(client: httpx.AsyncClient) -> Account:
    return await register(client)


@pytest.fixture
async def other_account(
    client_factory: Callable[[], httpx.AsyncClient],
) -> AsyncIterator[Account]:
    async with client_factory() as other:
        yield await register(other, email="someone.else@example.com", name="Someone Else")


async def upload(
    client: httpx.AsyncClient, data: bytes = WEBM_AUDIO, **params: str
) -> httpx.Response:
    return await client.post(
        "/api/v1/sessions", content=data, params=params, headers={"Content-Type": "audio/webm"}
    )


@pytest.fixture
def run_worker(services: Services) -> Callable[[], Awaitable[int]]:
    """Processes queued jobs until the queue is empty; returns how many ran."""

    async def run() -> int:
        worker = Worker(services, worker_id="test-worker")
        count = 0
        while await worker.run_once():
            count += 1
        return count

    return run


@pytest.fixture
def ready_session(
    account: Account, run_worker: Callable[[], Awaitable[int]]
) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def make(**params: str) -> dict[str, Any]:
        response = await upload(account.client, **params)
        assert response.status_code == 202, response.text
        await run_worker()
        detail = await account.client.get(f"/api/v1/sessions/{response.json()['id']}")
        assert detail.json()["status"] == "ready", detail.text
        result: dict[str, Any] = detail.json()
        return result

    return make


async def db_user(services: Services, email: str) -> User:
    async with services.sessionmaker() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user is not None
        return user


async def db_session(services: Services, session_id: str) -> TrainingSession | None:
    async with services.sessionmaker() as db:
        return await db.get(
            TrainingSession,
            uuid.UUID(session_id),
            options=[undefer(TrainingSession.transcript), undefer(TrainingSession.quiz)],
        )
