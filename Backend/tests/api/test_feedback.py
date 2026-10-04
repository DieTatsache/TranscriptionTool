"""Listener feedback: anonymous submission through share links, results for the owner."""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from sonora.container import Services
from sonora.models import FeedbackResponse
from sonora.services import feedback as feedback_service
from tests.conftest import Account

ReadySession = Callable[..., Awaitable[dict[str, Any]]]
COOKIE = "__Host-sonora_participant"
# Option indexes: 4 stars, 6/7 clarity, "Just right", 7/7 relevance.
RATINGS = {"overall": 3, "clarity": 5, "pace": 1, "relevance": 6}


@pytest.fixture
async def session_id(ready_session: ReadySession) -> str:
    return str((await ready_session())["id"])


async def share(account: Account, session_id: str, tabs: list[str]) -> str:
    response = await account.client.post(
        f"/api/v1/sessions/{session_id}/shares", json={"tabs": tabs}
    )
    assert response.status_code == 201, response.text
    token: str = response.json()["token"]
    return token


@pytest.fixture
async def token(account: Account, session_id: str) -> str:
    return await share(account, session_id, ["script", "feedback"])


@pytest.fixture
async def listener(client_factory: Any) -> Any:
    """A browser without an account (``client`` is the owner's browser)."""
    async with client_factory() as browser:
        yield browser


async def submit(
    listener: httpx.AsyncClient, token: str, ratings: Any = None, **body: Any
) -> httpx.Response:
    return await listener.post(
        f"/api/v1/public/shares/{token}/feedback",
        json={"ratings": RATINGS if ratings is None else ratings, **body},
    )


async def visit(listener: httpx.AsyncClient, token: str) -> httpx.Response:
    response = await listener.get(f"/api/v1/public/shares/{token}")
    assert response.status_code == 200, response.text
    return response


async def responses(services: Services) -> int:
    async with services.sessionmaker() as db:
        return await db.scalar(select(func.count()).select_from(FeedbackResponse)) or 0


class TestListener:
    async def test_the_share_page_serves_the_form_and_an_anonymous_cookie(
        self, token: str, client_factory: Any
    ) -> None:
        async with client_factory() as listener:
            response = await visit(listener, token)

        body = response.json()
        form = body["feedback_form"]
        assert form["version"] == 1
        assert [(q["id"], q["type"]) for q in form["questions"]] == [
            ("overall", "stars"),
            ("clarity", "scale"),
            ("pace", "choice"),
            ("relevance", "scale"),
            ("comment", "text"),
        ]
        assert form["questions"][2]["options"] == ["Too slow", "Just right", "Too fast"]
        assert form["questions"][4]["max_length"] == 800
        assert form["questions"][4]["required"] is False
        assert body["feedback_submitted"] is False
        assert body["viewer_is_owner"] is False
        cookie = response.headers["set-cookie"].lower()
        assert cookie.startswith(COOKIE.lower() + "=")
        for attribute in ("httponly", "secure", "samesite=strict", "path=/", "max-age=31536000"):
            assert attribute in cookie

    async def test_links_that_collect_nothing_set_no_cookie(
        self, account: Account, session_id: str, client_factory: Any
    ) -> None:
        token = await share(account, session_id, ["script", "transcript"])
        async with client_factory() as listener:
            response = await visit(listener, token)
        assert response.json()["feedback_form"] is None
        assert "set-cookie" not in response.headers

    async def test_each_listener_can_respond_once(
        self, token: str, client_factory: Any, services: Services
    ) -> None:
        async with client_factory() as listener:
            await visit(listener, token)
            first_cookie = listener.cookies[COOKIE]
            assert (await submit(listener, token, comment="Great examples!")).status_code == 204
            assert (await visit(listener, token)).json()["feedback_submitted"] is True
            assert listener.cookies[COOKIE] == first_cookie  # kept, not re-issued
            again = await submit(listener, token)
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "feedback_already_submitted"

        async with client_factory() as other_listener:
            await visit(other_listener, token)
            assert (await submit(other_listener, token)).status_code == 204
        assert await responses(services) == 2

    async def test_a_concurrent_duplicate_is_caught_by_the_database(
        self, token: str, client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async with client_factory() as listener:
            await visit(listener, token)
            assert (await submit(listener, token)).status_code == 204

            async def never_responded(*_: Any) -> bool:  # as if both requests raced
                return False

            monkeypatch.setattr(feedback_service, "has_responded", never_responded)
            again = await submit(listener, token)
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "feedback_already_submitted"

    async def test_requires_the_participant_cookie(
        self, token: str, listener: httpx.AsyncClient
    ) -> None:
        response = await submit(listener, token)  # never visited the page
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "participant_required"
        listener.cookies.set(COOKIE, "forged<script>", domain="testserver")
        assert (await submit(listener, token)).status_code == 400

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            ({"ratings": {"overall": 3, "clarity": 5, "pace": 1}}, "feedback_incomplete"),
            ({"ratings": {**RATINGS, "bonus": 1}}, "feedback_incomplete"),
            ({"ratings": {**RATINGS, "overall": 5}}, "validation_error"),  # 5 stars = index 4
            ({"ratings": {**RATINGS, "pace": 3}}, "validation_error"),
            ({"ratings": {**RATINGS, "clarity": -1}}, "validation_error"),
            ({"ratings": {**RATINGS, "clarity": 10}}, "validation_error"),
            ({"ratings": {**RATINGS, "clarity": "high"}}, "validation_error"),
            ({"ratings": RATINGS, "comment": "x" * 801}, "validation_error"),
            ({"ratings": RATINGS, "name": "spy"}, "validation_error"),  # unknown fields
            ({}, "validation_error"),
        ],
    )
    async def test_validates_the_answers(
        self, token: str, listener: httpx.AsyncClient, body: dict[str, Any], code: str
    ) -> None:
        await visit(listener, token)
        response = await listener.post(f"/api/v1/public/shares/{token}/feedback", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == code

    async def test_comments_are_cleaned_and_blank_ones_dropped(
        self, account: Account, session_id: str, token: str, client_factory: Any
    ) -> None:
        for comment in ("  Line one\r\n\n\n\nLine two‮\x07  ", "   \n  "):
            async with client_factory() as listener:
                await visit(listener, token)
                assert (await submit(listener, token, comment=comment)).status_code == 204
        comments = (
            await account.client.get(f"/api/v1/sessions/{session_id}/feedback/comments")
        ).json()
        assert [c["comment"] for c in comments] == ["Line one\n\nLine two"]

    async def test_only_links_with_the_feedback_tab_accept_it(
        self, account: Account, session_id: str, listener: httpx.AsyncClient
    ) -> None:
        token = await share(account, session_id, ["quiz"])
        await visit(listener, token)  # sets the cookie (the quiz collects attempts)
        response = await submit(listener, token)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "share_not_found"

    async def test_the_owner_is_recognised_and_cannot_rate_their_session(
        self, account: Account, token: str
    ) -> None:
        response = await visit(account.client, token)
        assert response.json()["viewer_is_owner"] is True
        assert "set-cookie" not in response.headers  # no listener identity for the owner
        refused = await submit(account.client, token)
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "own_session"

    async def test_cross_site_submissions_are_blocked(
        self, token: str, listener: httpx.AsyncClient
    ) -> None:
        await visit(listener, token)
        response = await listener.post(
            f"/api/v1/public/shares/{token}/feedback",
            json={"ratings": RATINGS},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_not_allowed"

    async def test_rate_limited_per_listener(self, token: str, listener: httpx.AsyncClient) -> None:
        await visit(listener, token)
        assert (await submit(listener, token)).status_code == 204
        for _ in range(9):
            assert (await submit(listener, token)).status_code == 409
        assert (await submit(listener, token)).status_code == 429

    async def test_capped_per_session(
        self, token: str, client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(feedback_service, "MAX_RESPONSES_PER_SESSION", 1)
        for expected in (204, 409):
            async with client_factory() as listener:
                await visit(listener, token)
                response = await submit(listener, token)
                assert response.status_code == expected
        assert response.json()["error"]["code"] == "feedback_closed"

    async def test_stores_only_per_session_pseudonyms(
        self,
        account: Account,
        token: str,
        ready_session: ReadySession,
        client_factory: Any,
        services: Services,
    ) -> None:
        second = await share(account, str((await ready_session())["id"]), ["feedback"])
        async with client_factory() as listener:
            for link in (token, second):
                await visit(listener, link)
                assert (await submit(listener, link)).status_code == 204
            raw = listener.cookies[COOKIE]
        async with services.sessionmaker() as db:
            keys = list(await db.scalars(select(FeedbackResponse.participant_key)))
        assert len(keys) == 2
        assert len(set(keys)) == 2  # the same browser can't be linked across sessions
        assert raw not in keys


class TestOwnerResults:
    async def test_summary_counts_every_option(
        self, account: Account, session_id: str, token: str, client_factory: Any
    ) -> None:
        answers = [
            ({"overall": 4, "clarity": 6, "pace": 1, "relevance": 6}, "Loved it"),
            ({"overall": 3, "clarity": 4, "pace": 2, "relevance": 5}, None),
            ({"overall": 4, "clarity": 6, "pace": 1, "relevance": 3}, "Slower please"),
        ]
        for ratings, comment in answers:
            async with client_factory() as listener:
                await visit(listener, token)
                assert (await submit(listener, token, ratings, comment=comment)).status_code == 204

        summary = (await account.client.get(f"/api/v1/sessions/{session_id}/feedback")).json()

        assert summary["responses"] == 3
        assert summary["comments"] == 2
        overall, clarity, pace, relevance = summary["questions"]
        assert overall["id"] == "overall"
        assert overall["label"] == "Overall session quality"
        assert overall["options"] == ["Poor", "Fair", "Good", "Very good", "Excellent"]
        assert overall["counts"] == [0, 0, 0, 1, 2]
        assert overall["answered"] == 3
        assert overall["average"] == pytest.approx(4.67)  # (4 + 5 + 5) / 3 stars
        assert clarity["counts"] == [0, 0, 0, 0, 1, 0, 2]
        assert (clarity["low"], clarity["high"]) == ("Very unclear", "Crystal clear")
        assert pace["counts"] == [0, 2, 1]
        assert pace["average"] is None  # not a numeric scale
        assert relevance["average"] == pytest.approx(5.67)
        assert all(q["type"] != "text" for q in summary["questions"])

    async def test_empty_summary(self, account: Account, session_id: str) -> None:
        summary = (await account.client.get(f"/api/v1/sessions/{session_id}/feedback")).json()
        assert summary["responses"] == 0
        assert summary["comments"] == 0
        assert summary["questions"][0]["counts"] == [0] * 5
        assert summary["questions"][0]["average"] is None

    async def test_comments_are_paginated_newest_first(
        self, account: Account, session_id: str, token: str, client_factory: Any
    ) -> None:
        for text in ("first", "second", "third"):
            async with client_factory() as listener:
                await visit(listener, token)
                await submit(listener, token, comment=text)
        path = f"/api/v1/sessions/{session_id}/feedback/comments"
        page = (await account.client.get(path, params={"limit": 2})).json()
        assert [c["comment"] for c in page] == ["third", "second"]
        assert set(page[0]) == {"id", "comment", "created_at"}  # nothing that identifies anyone
        rest = (await account.client.get(path, params={"limit": 2, "offset": 2})).json()
        assert [c["comment"] for c in rest] == ["first"]
        assert (await account.client.get(path, params={"limit": 101})).status_code == 422

    async def test_owner_can_remove_a_response(
        self,
        account: Account,
        session_id: str,
        token: str,
        client_factory: Any,
        services: Services,
    ) -> None:
        async with client_factory() as listener:
            await visit(listener, token)
            await submit(listener, token, comment="spam spam spam")
        (comment,) = (
            await account.client.get(f"/api/v1/sessions/{session_id}/feedback/comments")
        ).json()
        path = f"/api/v1/sessions/{session_id}/feedback/{comment['id']}"

        assert (await account.client.delete(path)).status_code == 204
        assert await responses(services) == 0
        assert (await account.client.delete(path)).status_code == 404

    async def test_results_are_private_to_the_owner(
        self,
        account: Account,
        other_account: Account,
        session_id: str,
        token: str,
        client_factory: Any,
    ) -> None:
        async with client_factory() as listener:
            await visit(listener, token)
            await submit(listener, token, comment="private")
            assert (
                await listener.get(f"/api/v1/sessions/{session_id}/feedback")
            ).status_code == 401
        (comment,) = (
            await account.client.get(f"/api/v1/sessions/{session_id}/feedback/comments")
        ).json()
        base = f"/api/v1/sessions/{session_id}/feedback"
        for method, path in [
            ("GET", base),
            ("GET", f"{base}/comments"),
            ("DELETE", f"{base}/{comment['id']}"),
        ]:
            response = await other_account.client.request(method, path)
            assert response.status_code == 404, (method, path)

    async def test_deleting_a_response_needs_csrf(
        self, account: Account, session_id: str, token: str, client_factory: Any
    ) -> None:
        async with client_factory() as listener:
            await visit(listener, token)
            await submit(listener, token, comment="keep me")
        (comment,) = (
            await account.client.get(f"/api/v1/sessions/{session_id}/feedback/comments")
        ).json()
        del account.client.headers["X-CSRF-Token"]
        response = await account.client.delete(
            f"/api/v1/sessions/{session_id}/feedback/{comment['id']}"
        )
        assert response.status_code == 403

    async def test_feedback_is_deleted_with_the_session(
        self,
        account: Account,
        session_id: str,
        token: str,
        client_factory: Any,
        services: Services,
    ) -> None:
        async with client_factory() as listener:
            await visit(listener, token)
            await submit(listener, token)
        await account.client.delete(f"/api/v1/sessions/{session_id}")
        assert await responses(services) == 0
