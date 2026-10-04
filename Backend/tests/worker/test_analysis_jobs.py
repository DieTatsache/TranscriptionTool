"""The ``analyze_session`` job: retries, failures and races, without touching the session."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select, update

from sonora.ai.llm import LLMBadResponse, LLMMessage, LLMUnavailable
from sonora.container import Services
from sonora.db import utcnow
from sonora.models import (
    AnalysisStatus,
    Job,
    JobStatus,
    JobType,
    SessionAnalysis,
    SessionStatus,
    TrainingSession,
)
from sonora.worker.pipeline import ANALYSIS_FAILURE
from sonora.worker.runner import Worker
from tests.conftest import Account, db_session, upload
from tests.fakes import FakeLLM, default_output

RunWorker = Callable[[], Awaitable[int]]


def failing_analysis(error: Exception) -> Callable[[list[LLMMessage], dict[str, Any]], Any]:
    """Script and quiz work; the analysis calls fail."""

    def handler(_messages: list[LLMMessage], schema: dict[str, Any]) -> Any:
        properties = schema["properties"]
        return error if "topics" in properties or "rhetoric" in properties else None

    def reply(messages: list[LLMMessage], schema: dict[str, Any]) -> Any:
        return handler(messages, schema) or default_output(schema)

    return reply


async def processed_session(account: Account, services: Services) -> str:
    session_id = str((await upload(account.client)).json()["id"])
    assert await Worker(services, worker_id="test").run_once()  # processing only
    return session_id


async def analysis_of(services: Services, session_id: str) -> SessionAnalysis:
    async with services.sessionmaker() as db:
        analysis = await db.get(SessionAnalysis, uuid.UUID(session_id))
    assert analysis is not None
    return analysis


async def analysis_job(services: Services) -> Job:
    async with services.sessionmaker() as db:
        job = await db.scalar(select(Job).where(Job.type == JobType.ANALYZE_SESSION))
    assert job is not None
    return job


async def make_due(services: Services) -> None:
    async with services.sessionmaker() as db:
        await db.execute(update(Job).values(run_after=utcnow() - timedelta(seconds=1)))
        await db.commit()


async def test_outages_are_retried_then_fail_the_analysis_only(
    account: Account, services: Services, llm: FakeLLM, run_worker: RunWorker
) -> None:
    session_id = await processed_session(account, services)
    llm.handler = failing_analysis(LLMUnavailable("connection refused"))

    await run_worker()
    assert (await analysis_of(services, session_id)).status is AnalysisStatus.QUEUED
    assert (await analysis_job(services)).status is JobStatus.PENDING
    for _ in range(2):  # attempts 2 and 3
        await make_due(services)
        await run_worker()

    analysis = await analysis_of(services, session_id)
    assert analysis.status is AnalysisStatus.FAILED
    assert analysis.error_message == ANALYSIS_FAILURE
    assert analysis.result is None
    session = await db_session(services, session_id)
    assert session is not None
    assert session.status is SessionStatus.READY  # script and quiz stay available
    assert session.error_message is None

    # The owner can ask again once the model is back.
    llm.handler = None
    response = await account.client.post(f"/api/v1/sessions/{session_id}/analysis")
    assert response.status_code == 202
    await run_worker()
    assert (await analysis_of(services, session_id)).status is AnalysisStatus.READY


async def test_unusable_output_is_retried_as_a_new_attempt(
    account: Account, services: Services, llm: FakeLLM, run_worker: RunWorker
) -> None:
    session_id = await processed_session(account, services)
    llm.queue.extend([LLMBadResponse("junk")] * 3)  # exhausts the analyzer's own retries

    await run_worker()
    assert (await analysis_of(services, session_id)).status is AnalysisStatus.QUEUED
    await make_due(services)
    await run_worker()
    assert (await analysis_of(services, session_id)).status is AnalysisStatus.READY


async def test_an_abandoned_last_attempt_fails_the_analysis_not_the_session(
    account: Account, services: Services
) -> None:
    session_id = await processed_session(account, services)
    async with services.sessionmaker() as db:
        await db.execute(
            update(Job)
            .where(Job.type == JobType.ANALYZE_SESSION)
            .values(
                status=JobStatus.RUNNING,
                attempts=3,
                locked_by="dead-worker",
                locked_until=utcnow() - timedelta(seconds=1),
            )
        )
        await db.execute(update(SessionAnalysis).values(status=AnalysisStatus.RUNNING))
        await db.commit()

    await Worker(services).maintenance()

    assert (await analysis_job(services)).status is JobStatus.FAILED
    assert (await analysis_of(services, session_id)).status is AnalysisStatus.FAILED
    session = await db_session(services, session_id)
    assert session is not None and session.status is SessionStatus.READY


async def test_session_deleted_during_the_analysis(
    account: Account, services: Services, llm: FakeLLM, run_worker: RunWorker
) -> None:
    session_id = await processed_session(account, services)

    async def owner_deletes_session() -> None:
        llm.before_reply = None
        async with services.sessionmaker() as db:
            await db.execute(
                delete(TrainingSession).where(TrainingSession.id == uuid.UUID(session_id))
            )
            await db.commit()

    llm.before_reply = owner_deletes_session
    assert await run_worker() == 1  # no crash when the result can't be saved
    async with services.sessionmaker() as db:
        assert await db.get(SessionAnalysis, uuid.UUID(session_id)) is None


async def test_a_job_without_its_analysis_row_does_nothing(
    account: Account, services: Services, llm: FakeLLM, run_worker: RunWorker
) -> None:
    session_id = await processed_session(account, services)
    async with services.sessionmaker() as db:
        await db.execute(delete(SessionAnalysis))
        await db.commit()
    calls = len(llm.calls)

    assert await run_worker() == 1

    assert len(llm.calls) == calls
    async with services.sessionmaker() as db:
        assert await db.get(SessionAnalysis, uuid.UUID(session_id)) is None


async def test_every_step_stops_quietly_when_its_row_vanished(
    account: Account,
    services: Services,
    llm: FakeLLM,
    transcriber: Any,
    monkeypatch: Any,
    caplog: Any,
) -> None:
    """The status saves before the slow steps report a deleted row: nothing runs after them."""
    from sonora.worker import pipeline

    async def vanished(_db: Any) -> bool:
        return False

    monkeypatch.setattr(pipeline, "_save", vanished)
    session_id = str((await upload(account.client)).json()["id"])
    assert await Worker(services, worker_id="w").run_once()  # stops at TRANSCRIBING
    assert transcriber.calls == []

    async with services.sessionmaker() as db:  # transcript present: stops at GENERATING
        await db.execute(
            update(TrainingSession).values(transcript=[{"start": 0, "end": 5, "text": "Hi."}])
        )
        await db.execute(update(Job).values(status=JobStatus.PENDING, attempts=0))
        await db.commit()
    assert await Worker(services, worker_id="w").run_once()
    assert llm.calls == []

    async with services.sessionmaker() as db:  # analysis: stops at RUNNING
        db.add(SessionAnalysis(session_id=uuid.UUID(session_id), status=AnalysisStatus.QUEUED))
        db.add(
            Job(
                type=JobType.ANALYZE_SESSION,
                session_id=uuid.UUID(session_id),
                status=JobStatus.PENDING,
                max_attempts=3,
            )
        )
        await db.commit()
    assert await Worker(services, worker_id="w").run_once()
    assert llm.calls == []
    assert "crashed" not in caplog.text
