"""First quiz attempts of anonymous listeners and the owner's per-question statistics."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from sonora.container import Services
from sonora.models import QuizAttempt
from sonora.services import quiz as quiz_service
from tests.conftest import Account, db_session, upload

ReadySession = Callable[..., Awaitable[dict[str, Any]]]


@pytest.fixture
async def session_id(ready_session: ReadySession) -> str:
    return str((await ready_session())["id"])


@pytest.fixture
async def token(account: Account, session_id: str) -> str:
    response = await account.client.post(
        f"/api/v1/sessions/{session_id}/shares", json={"tabs": ["quiz"]}
    )
    token: str = response.json()["token"]
    return token


@pytest.fixture
async def correct(services: Services, session_id: str) -> list[int]:
    stored = await db_session(services, session_id)
    assert stored is not None and stored.quiz is not None
    return [int(q["correct_option"]) for q in stored.quiz]


def wrong(option: int) -> int:
    return (option + 1) % 4


async def take(listener: httpx.AsyncClient, token: str, answers: list[int | None]) -> Any:
    response = await listener.post(
        f"/api/v1/public/shares/{token}/quiz/check", json={"answers": answers}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def attempts(services: Services) -> int:
    async with services.sessionmaker() as db:
        return await db.scalar(select(func.count()).select_from(QuizAttempt)) or 0


class TestRecording:
    async def test_only_the_first_attempt_of_a_listener_counts(
        self, token: str, correct: list[int], client_factory: Any, services: Services
    ) -> None:
        async with client_factory() as listener:
            await listener.get(f"/api/v1/public/shares/{token}")
            first = await take(listener, token, [wrong(correct[0]), *correct[1:]])
            second = await take(listener, token, correct)  # "Try again" is still graded

        assert (first["score"], first["counted"]) == (2, True)
        assert (second["score"], second["counted"]) == (3, False)
        async with services.sessionmaker() as db:
            stored = await db.scalar(select(QuizAttempt))
        assert stored is not None
        assert stored.answers == [wrong(correct[0]), *correct[1:]]
        assert (stored.score, stored.total) == (2, 3)

    async def test_the_owner_is_never_counted(
        self, account: Account, session_id: str, token: str, correct: list[int], services: Services
    ) -> None:
        own = await account.client.post(
            f"/api/v1/sessions/{session_id}/quiz/check", json={"answers": correct}
        )
        assert own.json()["counted"] is False
        via_link = await take(account.client, token, correct)  # signed in on their own link
        assert via_link["counted"] is False
        assert await attempts(services) == 0

    async def test_clients_without_the_cookie_are_graded_but_not_counted(
        self, token: str, correct: list[int], client_factory: Any, services: Services
    ) -> None:
        async with client_factory() as script:
            result = await take(script, token, correct)
        assert (result["score"], result["counted"]) == (3, False)
        assert await attempts(services) == 0

    async def test_a_concurrent_first_attempt_is_caught_by_the_database(
        self,
        token: str,
        correct: list[int],
        client_factory: Any,
        services: Services,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async with client_factory() as listener:
            await listener.get(f"/api/v1/public/shares/{token}")
            assert (await take(listener, token, correct))["counted"] is True

            async def never_attempted(*_: Any) -> bool:  # as if both requests raced
                return False

            monkeypatch.setattr(quiz_service, "has_attempted", never_attempted)
            assert (await take(listener, token, correct))["counted"] is False
        assert await attempts(services) == 1

    async def test_recording_is_capped_per_session(
        self,
        token: str,
        correct: list[int],
        client_factory: Any,
        services: Services,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(quiz_service, "MAX_RECORDED_ATTEMPTS", 1)
        for expected in (True, False):
            async with client_factory() as listener:
                await listener.get(f"/api/v1/public/shares/{token}")
                assert (await take(listener, token, correct))["counted"] is expected
        assert await attempts(services) == 1

    async def test_checks_are_rate_limited_per_listener(
        self, token: str, correct: list[int], client_factory: Any
    ) -> None:
        async with client_factory() as listener:
            await listener.get(f"/api/v1/public/shares/{token}")
            for _ in range(30):
                await take(listener, token, correct)
            limited = await listener.post(
                f"/api/v1/public/shares/{token}/quiz/check", json={"answers": correct}
            )
        assert limited.status_code == 429

    async def test_attempts_are_deleted_with_the_session(
        self,
        account: Account,
        session_id: str,
        token: str,
        correct: list[int],
        client_factory: Any,
        services: Services,
    ) -> None:
        async with client_factory() as listener:
            await listener.get(f"/api/v1/public/shares/{token}")
            await take(listener, token, correct)
        await account.client.delete(f"/api/v1/sessions/{session_id}")
        assert await attempts(services) == 0


class TestOwnerStatistics:
    async def test_per_question_answer_distribution(
        self,
        account: Account,
        session_id: str,
        token: str,
        correct: list[int],
        client_factory: Any,
    ) -> None:
        first_attempts: list[list[int | None]] = [
            list(correct),  # 3/3
            [wrong(correct[0]), correct[1], correct[2]],  # 2/3
            [wrong(correct[0]), wrong(correct[1]), None],  # 0/3, skipped the last
        ]
        for answers in first_attempts:
            async with client_factory() as listener:
                await listener.get(f"/api/v1/public/shares/{token}")
                await take(listener, token, answers)

        stats = (await account.client.get(f"/api/v1/sessions/{session_id}/quiz/results")).json()

        assert stats["attempts"] == 3
        assert stats["total"] == 3
        assert stats["average_score"] == pytest.approx(5 / 3, abs=0.01)
        assert stats["score_distribution"] == [1, 0, 1, 1]
        q1, q2, q3 = stats["questions"]
        assert q1["correct_option"] == correct[0]
        assert q1["question"] == "Question 1?"
        assert len(q1["options"]) == 4
        assert q1["option_counts"][correct[0]] == 1
        assert q1["option_counts"][wrong(correct[0])] == 2
        assert q1["answered"] == 3
        assert q2["option_counts"][correct[1]] == 2
        assert q3["answered"] == 2  # skipped questions count in no option
        assert sum(q3["option_counts"]) == 2

    async def test_no_attempts_yet(self, account: Account, session_id: str) -> None:
        stats = (await account.client.get(f"/api/v1/sessions/{session_id}/quiz/results")).json()
        assert stats["attempts"] == 0
        assert stats["average_score"] is None
        assert stats["score_distribution"] == [0, 0, 0, 0]
        assert all(q["answered"] == 0 for q in stats["questions"])

    async def test_needs_a_finished_quiz(self, account: Account) -> None:
        created = (await upload(account.client)).json()
        response = await account.client.get(f"/api/v1/sessions/{created['id']}/quiz/results")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "quiz_unavailable"

    async def test_private_to_the_owner(
        self, session_id: str, other_account: Account, client_factory: Any
    ) -> None:
        path = f"/api/v1/sessions/{session_id}/quiz/results"
        assert (await other_account.client.get(path)).status_code == 404
        async with client_factory() as anonymous:
            assert (await anonymous.get(path)).status_code == 401
