from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update

from sonora.container import Services
from sonora.db import utcnow
from sonora.models import ActivityEvent, ActivityType, ShareLink
from tests.conftest import Account, db_session, upload

ReadySession = Callable[..., Awaitable[dict[str, Any]]]


async def share(account: Account, session_id: str, **body: Any) -> httpx.Response:
    return await account.client.post(f"/api/v1/sessions/{session_id}/shares", json=body)


@pytest.fixture
async def session_id(ready_session: ReadySession) -> str:
    return str((await ready_session())["id"])


class TestOwnerSide:
    async def test_creates_and_lists_links(
        self, account: Account, session_id: str, services: Services
    ) -> None:
        response = await share(account, session_id, tabs=["transcript", "script", "script"])

        assert response.status_code == 201
        link = response.json()
        assert link["tabs"] == ["script", "transcript"]  # de-duplicated, canonical order
        assert len(link["token"]) >= 43
        assert link["expires_at"] is not None  # 30 days by default
        listed = (await account.client.get(f"/api/v1/sessions/{session_id}/shares")).json()
        assert [item["id"] for item in listed] == [link["id"]]
        async with services.sessionmaker() as db:
            detail = await db.scalar(
                select(ActivityEvent.detail).where(ActivityEvent.type == ActivityType.SHARE_CREATED)
            )
        assert detail is not None and detail.endswith("script, transcript")

    async def test_links_can_be_permanent(self, account: Account, session_id: str) -> None:
        link = (await share(account, session_id, tabs=["quiz"], expires_in_days=None)).json()
        assert link["expires_at"] is None

    @pytest.mark.parametrize(
        "body",
        [{"tabs": []}, {"tabs": ["video"]}, {"tabs": ["quiz"], "expires_in_days": 0}, {}],
    )
    async def test_validates_input(
        self, account: Account, session_id: str, body: dict[str, Any]
    ) -> None:
        response = await share(account, session_id, **body)
        assert response.status_code == 422

    async def test_only_finished_sessions_can_be_shared(self, account: Account) -> None:
        created = (await upload(account.client)).json()
        response = await share(account, created["id"], tabs=["quiz"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "session_not_ready"

    async def test_number_of_links_is_capped(self, account: Account, session_id: str) -> None:
        for _ in range(20):
            assert (await share(account, session_id, tabs=["quiz"])).status_code == 201
        response = await share(account, session_id, tabs=["quiz"])
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "too_many_links"

    async def test_revoke(
        self, account: Account, session_id: str, client: httpx.AsyncClient
    ) -> None:
        link = (await share(account, session_id, tabs=["script"])).json()

        response = await account.client.delete(f"/api/v1/sessions/{session_id}/shares/{link['id']}")

        assert response.status_code == 204
        assert (await client.get(f"/api/v1/public/shares/{link['token']}")).status_code == 404
        again = await account.client.delete(f"/api/v1/sessions/{session_id}/shares/{link['id']}")
        assert again.status_code == 404


class TestParticipantSide:
    async def test_sees_only_the_shared_tabs(
        self, account: Account, session_id: str, client_factory: Any
    ) -> None:
        token = (await share(account, session_id, tabs=["script"])).json()["token"]

        async with client_factory() as participant:  # no account, no cookies
            response = await participant.get(f"/api/v1/public/shares/{token}")

        assert response.status_code == 200
        body = response.json()
        assert body["tabs"] == ["script"]
        assert body["title"] == "Handling Objections"
        assert body["script"]["summary"]
        assert body["quiz"] is None
        assert body["transcript"] is None

    async def test_quiz_is_shown_without_answers_and_graded_on_the_server(
        self, account: Account, session_id: str, client_factory: Any, services: Services
    ) -> None:
        token = (await share(account, session_id, tabs=["quiz", "transcript"])).json()["token"]
        stored = await db_session(services, session_id)
        assert stored is not None and stored.quiz is not None
        correct = [q["correct_option"] for q in stored.quiz]

        async with client_factory() as participant:
            shared = (await participant.get(f"/api/v1/public/shares/{token}")).json()
            assert all(set(q) == {"question", "options"} for q in shared["quiz"])
            assert shared["transcript"][0]["text"].startswith("Welcome back")
            result = await participant.post(
                f"/api/v1/public/shares/{token}/quiz/check", json={"answers": correct}
            )

        assert result.status_code == 200
        assert result.json()["score"] == 3

    async def test_quiz_grading_requires_the_quiz_to_be_shared(
        self, account: Account, session_id: str, client: httpx.AsyncClient
    ) -> None:
        token = (await share(account, session_id, tabs=["script"])).json()["token"]
        response = await client.post(
            f"/api/v1/public/shares/{token}/quiz/check", json={"answers": [0, 0, 0]}
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("token", ["short", "x" * 43, "a*b" + "c" * 40, "x" * 128])
    async def test_unknown_or_malformed_tokens_are_not_found(
        self, client: httpx.AsyncClient, token: str
    ) -> None:
        response = await client.get(f"/api/v1/public/shares/{token}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "share_not_found"

    async def test_path_tricks_do_not_reach_other_resources(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/v1/public/shares/..%2F..%2Fsessions")
        assert response.status_code == 404

    async def test_expired_links_stop_working(
        self, account: Account, session_id: str, client: httpx.AsyncClient, services: Services
    ) -> None:
        token = (await share(account, session_id, tabs=["script"])).json()["token"]
        async with services.sessionmaker() as db:
            await db.execute(update(ShareLink).values(expires_at=utcnow() - timedelta(seconds=1)))
            await db.commit()
        assert (await client.get(f"/api/v1/public/shares/{token}")).status_code == 404
        listed = (await account.client.get(f"/api/v1/sessions/{session_id}/shares")).json()
        assert listed == []

    async def test_deleting_the_session_kills_its_links(
        self, account: Account, session_id: str, client: httpx.AsyncClient
    ) -> None:
        token = (await share(account, session_id, tabs=["script"])).json()["token"]
        await account.client.delete(f"/api/v1/sessions/{session_id}")
        assert (await client.get(f"/api/v1/public/shares/{token}")).status_code == 404

    async def test_public_reads_are_rate_limited(
        self, account: Account, session_id: str, client_factory: Any
    ) -> None:
        token = (await share(account, session_id, tabs=["script"])).json()["token"]
        async with client_factory() as participant:
            for _ in range(60):
                assert (await participant.get(f"/api/v1/public/shares/{token}")).status_code == 200
            assert (await participant.get(f"/api/v1/public/shares/{token}")).status_code == 429
