import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select, update

from sonora.ai.llm import LLMBadResponse, LLMUnavailable
from sonora.container import Services
from sonora.db import utcnow
from sonora.models import AuthSession, Job, JobStatus, SessionStatus, TrainingSession
from sonora.transcription import AudioTooLong, NoSpeechDetected, TranscriptionError
from sonora.worker import queue
from sonora.worker.runner import GENERIC_FAILURE, INTERRUPTED_FAILURE, Worker, retry_delay
from tests.conftest import Account, db_session, upload
from tests.fakes import FakeLLM, FakeTranscriber

RunWorker = Callable[[], Awaitable[int]]


async def queued_session(account: Account) -> str:
    response = await upload(account.client)
    assert response.status_code == 202
    return str(response.json()["id"])


async def jobs(services: Services) -> list[Job]:
    async with services.sessionmaker() as db:
        return list((await db.scalars(select(Job).order_by(Job.created_at))).all())


async def make_due(services: Services) -> None:
    async with services.sessionmaker() as db:
        await db.execute(update(Job).values(run_after=utcnow() - timedelta(seconds=1)))
        await db.commit()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (NoSpeechDetected("x"), "No speech was detected in the recording."),
        (AudioTooLong("x"), "The recording is longer than the 180-minute limit."),
        (
            TranscriptionError("x"),
            "The recording could not be decoded. Please upload a supported audio file.",
        ),
    ],
)
async def test_permanent_transcription_failures_are_not_retried(
    account: Account,
    services: Services,
    transcriber: FakeTranscriber,
    run_worker: RunWorker,
    error: Exception,
    message: str,
) -> None:
    session_id = await queued_session(account)
    transcriber.error = error

    assert await run_worker() == 1

    session = await db_session(services, session_id)
    assert session is not None
    assert session.status is SessionStatus.FAILED
    assert session.error_message == message
    assert [j.status for j in await jobs(services)] == [JobStatus.FAILED]
    assert session.audio_key is not None  # kept so the owner can retry


async def test_missing_audio_file_fails_permanently(
    account: Account, services: Services, run_worker: RunWorker
) -> None:
    session_id = await queued_session(account)
    for path in services.storage.directory.iterdir():
        path.unlink()
    await run_worker()
    session = await db_session(services, session_id)
    assert session is not None
    assert session.status is SessionStatus.FAILED
    assert session.error_message is not None and "no longer available" in session.error_message


async def test_llm_outages_are_retried_with_backoff_then_fail(
    account: Account,
    services: Services,
    llm: FakeLLM,
    run_worker: RunWorker,
    transcriber: FakeTranscriber,
) -> None:
    session_id = await queued_session(account)
    llm.handler = lambda _m, _s: LLMUnavailable("connection refused")

    await run_worker()
    session = await db_session(services, session_id)
    assert session is not None
    assert session.status is SessionStatus.QUEUED  # waiting for the retry
    assert session.transcript is not None  # transcription result was kept
    (job,) = await jobs(services)
    assert job.status is JobStatus.PENDING
    assert job.run_after > utcnow() + timedelta(seconds=20)

    for _ in range(2):  # attempts 2 and 3
        await make_due(services)
        await run_worker()
    session = await db_session(services, session_id)
    assert session is not None
    assert session.status is SessionStatus.FAILED
    assert session.error_message == GENERIC_FAILURE
    assert (await jobs(services))[0].status is JobStatus.FAILED
    assert len(transcriber.calls) == 1  # never transcribed twice


async def test_unusable_model_output_is_retried(
    account: Account, services: Services, llm: FakeLLM, run_worker: RunWorker
) -> None:
    session_id = await queued_session(account)
    llm.queue.extend([LLMBadResponse("junk")] * 3)  # exhausts the generator's own retries

    await run_worker()

    session = await db_session(services, session_id)
    assert session is not None and session.status is SessionStatus.QUEUED
    await make_due(services)
    await run_worker()
    session = await db_session(services, session_id)
    assert session is not None and session.status is SessionStatus.READY


async def test_unexpected_errors_are_retried(
    account: Account, services: Services, transcriber: FakeTranscriber, run_worker: RunWorker
) -> None:
    session_id = await queued_session(account)
    transcriber.error = MemoryError("out of memory")
    await run_worker()
    session = await db_session(services, session_id)
    assert session is not None and session.status is SessionStatus.QUEUED
    (job,) = await jobs(services)
    assert job.last_error is not None and "out of memory" in job.last_error


@pytest.mark.parametrize("settings_overrides", [{"keep_audio": True}])
async def test_audio_can_be_kept(
    account: Account, services: Services, run_worker: RunWorker
) -> None:
    session_id = await queued_session(account)
    await run_worker()
    session = await db_session(services, session_id)
    assert session is not None
    assert session.status is SessionStatus.READY
    assert session.audio_key is not None
    assert services.storage.path_for(session.audio_key).is_file()


async def delete_session(services: Services, session_id: str) -> None:
    async with services.sessionmaker() as db:
        await db.execute(delete(TrainingSession).where(TrainingSession.id == uuid.UUID(session_id)))
        await db.commit()


async def test_session_deleted_after_its_job_was_claimed(
    account: Account, services: Services, transcriber: FakeTranscriber
) -> None:
    session_id = await queued_session(account)
    async with services.sessionmaker() as db:
        job = await queue.claim_next(db, "w", lease_seconds=60)
    assert job is not None
    await delete_session(services, session_id)  # the job row cascades away too

    await Worker(services, worker_id="w")._execute(job)  # finishes quietly

    assert transcriber.calls == []
    assert await jobs(services) == []


async def test_session_deleted_during_generation(
    account: Account, services: Services, llm: FakeLLM, run_worker: RunWorker
) -> None:
    session_id = await queued_session(account)

    async def owner_deletes_session() -> None:
        llm.before_reply = None
        await delete_session(services, session_id)

    llm.before_reply = owner_deletes_session

    assert await run_worker() == 1  # no crash when the results can't be saved

    assert await db_session(services, session_id) is None
    assert await jobs(services) == []


def test_retry_delay_grows_and_is_capped() -> None:
    assert [retry_delay(n).total_seconds() for n in (1, 2, 3, 4, 10)] == [30, 120, 480, 1920, 3600]


async def test_run_loop_processes_work_and_stops(account: Account, services: Services) -> None:
    session_id = await queued_session(account)
    stop = asyncio.Event()
    task = asyncio.create_task(Worker(services, worker_id="loop").run(stop))
    for _ in range(200):
        session = await db_session(services, session_id)
        if session is not None and session.status is SessionStatus.READY:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    session = await db_session(services, session_id)
    assert session is not None and session.status is SessionStatus.READY


async def test_run_loop_survives_iteration_errors(
    services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    recovered = asyncio.Event()

    async def flaky(self: Worker) -> bool:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ConnectionError("database restarting")
        recovered.set()  # the loop kept going after the error
        return False

    monkeypatch.setattr(Worker, "run_once", flaky)
    stop = asyncio.Event()
    task = asyncio.create_task(Worker(services).run(stop))
    await asyncio.wait_for(recovered.wait(), timeout=5)
    stop.set()
    await asyncio.wait_for(task, timeout=5)


@pytest.mark.parametrize("settings_overrides", [{"job_lease_seconds": 30}])
async def test_lease_is_extended_while_a_job_runs(
    account: Account,
    services: Services,
    transcriber: FakeTranscriber,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await queued_session(account)
    # Make the heartbeat fire immediately and the transcription slow.
    real_sleep = asyncio.sleep
    monkeypatch.setattr("sonora.worker.runner.asyncio.sleep", lambda _s: real_sleep(0.01))
    original = transcriber.transcribe

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.2)
        return original(*args, **kwargs)

    monkeypatch.setattr(transcriber, "transcribe", slow)
    extended: list[bool] = []
    real_extend = queue.extend_lease

    async def spy(*args: Any, **kwargs: Any) -> bool:
        result = await real_extend(*args, **kwargs)
        extended.append(result)
        return result

    monkeypatch.setattr(queue, "extend_lease", spy)
    assert await Worker(services, worker_id="hb").run_once()
    assert extended and all(extended)


class TestMaintenance:
    async def test_purges_expired_sign_ins(self, account: Account, services: Services) -> None:
        async with services.sessionmaker() as db:
            await db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(seconds=1)))
            await db.commit()
        await Worker(services).maintenance()
        async with services.sessionmaker() as db:
            assert await db.scalar(select(func.count()).select_from(AuthSession)) == 0

    async def test_fails_jobs_whose_worker_died_on_the_last_attempt(
        self, account: Account, services: Services
    ) -> None:
        session_id = await queued_session(account)
        async with services.sessionmaker() as db:
            await db.execute(
                update(Job).values(
                    status=JobStatus.RUNNING,
                    attempts=3,
                    locked_by="dead",
                    locked_until=utcnow() - timedelta(seconds=1),
                )
            )
            await db.commit()
        await Worker(services).maintenance()
        (job,) = await jobs(services)
        assert job.status is JobStatus.FAILED
        session = await db_session(services, session_id)
        assert session is not None
        assert session.status is SessionStatus.FAILED
        assert session.error_message == INTERRUPTED_FAILURE

    async def test_deletes_old_finished_jobs_only(
        self, account: Account, services: Services, run_worker: RunWorker
    ) -> None:
        await queued_session(account)
        await run_worker()
        await Worker(services).maintenance()
        assert len(await jobs(services)) == 1  # recent: kept
        async with services.sessionmaker() as db:
            await db.execute(update(Job).values(finished_at=utcnow() - timedelta(days=31)))
            await db.commit()
        await Worker(services).maintenance()
        assert await jobs(services) == []

    async def test_removes_orphaned_audio_but_not_live_or_recent_files(
        self, account: Account, services: Services
    ) -> None:
        session_id = await queued_session(account)
        session = await db_session(services, session_id)
        assert session is not None and session.audio_key is not None
        directory = services.storage.directory
        old = time.time() - 7 * 3600
        orphan = directory / f"{uuid.uuid4().hex}.webm"
        fresh_partial = directory / f"{uuid.uuid4().hex}.part"
        for path in (orphan, fresh_partial):
            path.write_bytes(b"x")
        os.utime(orphan, (old, old))
        os.utime(directory / session.audio_key, (old, old))

        await Worker(services).maintenance()

        remaining = {p.name for p in directory.iterdir()}
        assert remaining == {session.audio_key, fresh_partial.name}


async def test_session_deleted_during_transcription(
    account: Account, services: Services, transcriber: FakeTranscriber, run_worker: RunWorker
) -> None:
    session_id = await queued_session(account)
    loop = asyncio.get_running_loop()
    transcribe = transcriber.transcribe

    def owner_deletes_while_transcribing(*args: Any, **kwargs: Any) -> Any:
        # Runs in the worker thread; the deletion happens on the event loop meanwhile.
        asyncio.run_coroutine_threadsafe(delete_session(services, session_id), loop).result(10)
        return transcribe(*args, **kwargs)

    transcriber.transcribe = owner_deletes_while_transcribing  # type: ignore[method-assign]

    assert await run_worker() == 1

    assert await db_session(services, session_id) is None
    assert await jobs(services) == []


@pytest.mark.parametrize("settings_overrides", [{"job_lease_seconds": 30}])
async def test_heartbeat_stops_when_the_job_disappears(
    account: Account,
    services: Services,
    transcriber: FakeTranscriber,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session_id = await queued_session(account)
    real_sleep = asyncio.sleep
    monkeypatch.setattr("sonora.worker.runner.asyncio.sleep", lambda _s: real_sleep(0.01))
    loop = asyncio.get_running_loop()
    transcribe = transcriber.transcribe

    def slow_and_deleted(*args: Any, **kwargs: Any) -> Any:
        asyncio.run_coroutine_threadsafe(delete_session(services, session_id), loop).result(10)
        time.sleep(0.2)  # give the heartbeat time to notice
        return transcribe(*args, **kwargs)

    transcriber.transcribe = slow_and_deleted  # type: ignore[method-assign]
    with caplog.at_level("INFO", logger="sonora.worker.runner"):
        assert await Worker(services, worker_id="hb").run_once()
    assert any("lost lease" in record.message for record in caplog.records)
