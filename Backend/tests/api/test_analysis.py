"""Lecture analysis endpoints (owner only)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import delete, func, select

from sonora.container import Services
from sonora.models import Job, SessionAnalysis
from sonora.worker.runner import Worker
from tests.conftest import Account, upload
from tests.fakes import FakeLLM

ReadySession = Callable[..., Awaitable[dict[str, Any]]]
RunWorker = Callable[[], Awaitable[int]]


def path(session_id: str) -> str:
    return f"/api/v1/sessions/{session_id}/analysis"


async def forget_analysis(services: Services, session_id: str) -> None:
    """As for sessions created before the analysis existed."""
    async with services.sessionmaker() as db:
        await db.execute(
            delete(SessionAnalysis).where(SessionAnalysis.session_id == uuid.UUID(session_id))
        )
        await db.commit()


async def test_new_sessions_are_analysed_after_processing(
    account: Account, services: Services
) -> None:
    session_id = (await upload(account.client)).json()["id"]
    worker = Worker(services, worker_id="test")
    assert await worker.run_once()  # transcript, script and quiz

    queued = (await account.client.get(path(session_id))).json()
    assert queued["status"] == "queued"
    assert queued["scores"] is None
    assert (await account.client.get(f"/api/v1/sessions/{session_id}")).json()["status"] == (
        "ready"  # the analysis never holds back the session
    )

    assert await worker.run_once()  # the analysis
    analysis = (await account.client.get(path(session_id))).json()

    assert analysis["status"] == "ready"
    assert analysis["model"] == FakeLLM.model
    assert analysis["completed_at"] is not None
    assert analysis["error_message"] is None
    assert {name: s["score"] for name, s in analysis["scores"].items()} == {
        "content": 8,
        "rhetoric": 6,
        "structure": 7,
    }
    assert analysis["scores"]["rhetoric"] == {
        "score": 6,
        "assessment": "Your rhetoric is solid.",
        "tip": "Polish your rhetoric.",
    }
    topics = analysis["topics"]
    assert [t["title"] for t in topics] == [
        "What an objection is",
        "Acknowledge, ask, reframe",
        "Silence and follow-up",
    ]
    assert topics[0]["start_seconds"] == 12
    assert all(t["duration_seconds"] == t["end_seconds"] - t["start_seconds"] for t in topics)
    assert analysis["metrics"]["words"] > 0
    assert analysis["metrics"]["words_per_minute"] > 0


async def test_sessions_without_an_analysis_can_request_one(
    account: Account, ready_session: ReadySession, services: Services, run_worker: RunWorker
) -> None:
    session_id = (await ready_session())["id"]
    await forget_analysis(services, session_id)
    assert (await account.client.get(path(session_id))).json() == {
        "status": "none",
        "error_message": None,
        "model": None,
        "completed_at": None,
        "scores": None,
        "topics": None,
        "metrics": None,
    }

    response = await account.client.post(path(session_id))

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    again = await account.client.post(path(session_id))  # already on its way: no second job
    assert again.status_code == 202
    async with services.sessionmaker() as db:
        assert (
            await db.scalar(select(func.count()).select_from(Job).where(Job.finished_at.is_(None)))
            == 1
        )
    assert await run_worker() == 1
    assert (await account.client.get(path(session_id))).json()["status"] == "ready"


async def test_a_finished_analysis_is_not_regenerated(
    account: Account, ready_session: ReadySession
) -> None:
    session_id = (await ready_session())["id"]
    response = await account.client.post(path(session_id))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "analysis_exists"


async def test_requires_a_ready_session(account: Account) -> None:
    session_id = (await upload(account.client)).json()["id"]
    assert (await account.client.get(path(session_id))).json()["status"] == "none"
    response = await account.client.post(path(session_id))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_ready"


async def test_requests_are_rate_limited(
    account: Account, ready_session: ReadySession, services: Services
) -> None:
    session_id = (await ready_session())["id"]
    for _ in range(10):
        await forget_analysis(services, session_id)
        assert (await account.client.post(path(session_id))).status_code == 202
    await forget_analysis(services, session_id)
    assert (await account.client.post(path(session_id))).status_code == 429


async def test_private_to_the_owner(
    account: Account,
    other_account: Account,
    ready_session: ReadySession,
    client_factory: Any,
) -> None:
    session_id = (await ready_session())["id"]
    for method in ("GET", "POST"):
        response = await other_account.client.request(method, path(session_id))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "session_not_found"
    async with client_factory() as anonymous:
        assert (await anonymous.get(path(session_id))).status_code == 401
    del account.client.headers["X-CSRF-Token"]
    assert (await account.client.post(path(session_id))).status_code == 403


async def test_never_part_of_share_links(account: Account, ready_session: ReadySession) -> None:
    session_id = (await ready_session())["id"]
    response = await account.client.post(
        f"/api/v1/sessions/{session_id}/shares", json={"tabs": ["analysis"]}
    )
    assert response.status_code == 422
    token = (
        await account.client.post(
            f"/api/v1/sessions/{session_id}/shares",
            json={"tabs": ["script", "quiz", "transcript", "feedback"]},
        )
    ).json()["token"]
    shared = (await account.client.get(f"/api/v1/public/shares/{token}")).text
    assert "rhetoric" not in shared
    assert "Your content is solid." not in shared


async def test_the_analysis_is_deleted_with_its_session(
    account: Account, ready_session: ReadySession, services: Services
) -> None:
    session_id = (await ready_session())["id"]
    await account.client.delete(f"/api/v1/sessions/{session_id}")
    async with services.sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(SessionAnalysis)) == 0
