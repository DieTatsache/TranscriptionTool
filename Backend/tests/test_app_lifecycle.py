"""Application startup/shutdown, the embedded worker and the standalone worker entrypoint."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import sonora.main
from sonora.container import Services, build_services
from sonora.db import Base
from sonora.main import create_app
from sonora.transcription.fake import FakeTranscriber as DevFakeTranscriber
from sonora.worker import __main__ as worker_main
from sonora.worker.runner import Worker
from tests.conftest import BASE_URL, make_settings, register, upload
from tests.fakes import FakeLLM, FakeTranscriber


async def wait_for_status(client: httpx.AsyncClient, session_id: str, status: str) -> None:
    for _ in range(300):
        if (await client.get(f"/api/v1/sessions/{session_id}")).json()["status"] == status:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"session never reached {status}")


@pytest.mark.parametrize(
    "settings_overrides", [{"worker_embedded": True, "worker_poll_seconds": 0.02}]
)
async def test_embedded_worker_processes_uploads(app: FastAPI) -> None:
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client,
    ):
        account = await register(client)
        session_id = (await upload(account.client)).json()["id"]
        await wait_for_status(client, session_id, "ready")


@pytest.mark.parametrize(
    "settings_overrides", [{"worker_embedded": True, "worker_poll_seconds": 0.02}]
)
async def test_shutdown_does_not_wait_for_a_busy_worker(
    app: FastAPI, llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sonora.main, "WORKER_SHUTDOWN_GRACE_SECONDS", 0.1)

    async def very_slow_model() -> None:
        await asyncio.sleep(60)

    llm.before_reply = very_slow_model
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        async with app.router.lifespan_context(app):
            account = await register(client)
            session_id = (await upload(account.client)).json()["id"]
            await wait_for_status(client, session_id, "generating")
            started = time.monotonic()
        assert time.monotonic() - started < 5  # cancelled after the grace period


async def test_create_app_builds_its_own_services(tmp_path: Path) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level  # create_app configures logging
    try:
        app = create_app(make_settings(tmp_path))
        services: Services = app.state.services
        async with services.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client,
        ):
            assert (await client.get("/api/v1/health/ready")).status_code == 200
        # Built from SONORA_TRANSCRIPTION_BACKEND=fake on first use.
        assert isinstance(services.transcriber, DevFakeTranscriber)
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


async def test_errors_after_the_response_started_are_not_masked(app: FastAPI) -> None:
    async def body() -> AsyncIterator[bytes]:
        yield b"partial"
        raise RuntimeError("stream broke")

    @app.get("/api/v1/_stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(body())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE_URL
    ) as client:
        with pytest.raises(RuntimeError, match="stream broke"):
            await client.get("/api/v1/_stream")


def test_standalone_worker_entrypoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(tmp_path)
    built: list[Services] = []
    ran: list[str] = []

    def build(settings_: Any) -> Services:
        services = build_services(settings_, llm=FakeLLM(), transcriber=FakeTranscriber())
        built.append(services)
        return services

    async def run(self: Worker, stop: asyncio.Event) -> None:
        ran.append(self.worker_id)

    monkeypatch.setattr(worker_main, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "build_services", build)
    monkeypatch.setattr(worker_main, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(Worker, "run", run)

    asyncio.run(worker_main.main())

    assert len(built) == 1
    assert len(ran) == 1
