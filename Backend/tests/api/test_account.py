import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from sonora.container import Services
from sonora.models import ActivityEvent, ActivityType, AuthSession, TrainingSession, User
from tests.conftest import PASSWORD, Account, db_user, upload

ReadySession = Callable[..., Awaitable[dict[str, Any]]]
NEW_PASSWORD = "maple-orbit-canvas-77"


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def activity_types(account: Account) -> list[str]:
    return [e["type"] for e in (await account.client.get("/api/v1/me/activity")).json()]


@pytest.fixture
async def second_browser(account: Account, client_factory: Any) -> Any:
    """The same user signed in on another device."""
    async with client_factory() as browser:
        assert (await login(browser, account.email, PASSWORD)).status_code == 200
        yield browser


class TestProfile:
    async def test_updates_profile_fields(self, account: Account) -> None:
        response = await account.client.patch(
            "/api/v1/me",
            json={
                "name": "Dr. Marie Tanner",
                "bio": "Line one\r\n\n\n\nLine two‮",
                "notify_on_ready": False,
            },
        )
        assert response.status_code == 200
        user = response.json()
        assert user["name"] == "Dr. Marie Tanner"
        assert user["bio"] == "Line one\n\nLine two"  # normalised newlines, bidi override removed
        assert user["notify_on_ready"] is False
        assert (await activity_types(account))[0] == "profile_updated"

    async def test_unchanged_values_are_not_logged(self, account: Account) -> None:
        await account.client.patch("/api/v1/me", json={"name": "Test Trainer"})
        assert await activity_types(account) == ["account_created"]

    @pytest.mark.parametrize(
        "body", [{"name": ""}, {"name": "x" * 101}, {"bio": "x" * 1001}, {"email": "nope"}]
    )
    async def test_validates_input(self, account: Account, body: dict[str, Any]) -> None:
        assert (await account.client.patch("/api/v1/me", json=body)).status_code == 422

    async def test_changing_email_requires_the_current_password(self, account: Account) -> None:
        for password in (None, "wrong-password-123"):
            response = await account.client.patch(
                "/api/v1/me", json={"email": "new@example.com", "current_password": password}
            )
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "invalid_password"
        assert (await account.client.get("/api/v1/auth/me")).json()["user"][
            "email"
        ] == account.email

    async def test_changing_email_signs_out_other_devices(
        self, account: Account, second_browser: httpx.AsyncClient
    ) -> None:
        response = await account.client.patch(
            "/api/v1/me", json={"email": "New@Example.com", "current_password": PASSWORD}
        )
        assert response.status_code == 200
        assert response.json()["email"] == "new@example.com"
        assert (await second_browser.get("/api/v1/auth/me")).status_code == 401
        assert (await account.client.get("/api/v1/auth/me")).status_code == 200
        assert "email_changed" in await activity_types(account)

    async def test_email_must_stay_unique(self, account: Account, other_account: Account) -> None:
        response = await account.client.patch(
            "/api/v1/me", json={"email": other_account.email, "current_password": PASSWORD}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_taken"


class TestPasswordChange:
    async def test_changes_password_and_signs_out_other_devices(
        self, account: Account, second_browser: httpx.AsyncClient, client_factory: Any
    ) -> None:
        response = await account.client.post(
            "/api/v1/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 204
        assert (await second_browser.get("/api/v1/auth/me")).status_code == 401
        assert (await account.client.get("/api/v1/auth/me")).status_code == 200
        async with client_factory() as browser:
            assert (await login(browser, account.email, PASSWORD)).status_code == 401
            assert (await login(browser, account.email, NEW_PASSWORD)).status_code == 200
        assert "password_changed" in await activity_types(account)

    @pytest.mark.parametrize(
        ("current", "new", "status", "code"),
        [
            ("wrong-password-1", NEW_PASSWORD, 403, "invalid_password"),
            (PASSWORD, "tiny", 422, "weak_password"),
            (PASSWORD, PASSWORD, 422, "weak_password"),
        ],
    )
    async def test_rejects_bad_requests(
        self, account: Account, current: str, new: str, status: int, code: str
    ) -> None:
        response = await account.client.post(
            "/api/v1/me/password", json={"current_password": current, "new_password": new}
        )
        assert response.status_code == status
        assert response.json()["error"]["code"] == code

    async def test_password_guessing_is_rate_limited(self, account: Account) -> None:
        for _ in range(5):
            response = await account.client.post(
                "/api/v1/me/password",
                json={"current_password": "guess-123456", "new_password": NEW_PASSWORD},
            )
            assert response.status_code == 403
        response = await account.client.post(
            "/api/v1/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        )
        assert response.status_code == 429


class TestAccountDeletion:
    async def test_requires_the_password(self, account: Account) -> None:
        response = await account.client.post(
            "/api/v1/me/delete", json={"password": "wrong-password-1"}
        )
        assert response.status_code == 403
        assert (await account.client.get("/api/v1/auth/me")).status_code == 200

    async def test_erases_everything_the_user_owns(
        self,
        account: Account,
        other_account: Account,
        ready_session: ReadySession,
        services: Services,
        client_factory: Any,
    ) -> None:
        await ready_session()
        await upload(account.client)  # pending audio on disk
        assert list(services.storage.directory.iterdir())
        await upload(other_account.client)

        response = await account.client.post("/api/v1/me/delete", json={"password": PASSWORD})

        assert response.status_code == 204
        assert "max-age=0" in response.headers["set-cookie"].lower()
        async with services.sessionmaker() as db:
            assert await db.scalar(select(func.count()).select_from(User)) == 1
            assert (
                await db.scalar(select(func.count()).select_from(TrainingSession)) == 1
            )  # other's
            assert await db.scalar(select(func.count()).select_from(AuthSession)) == 1
            owner_events = await db.scalar(
                select(func.count())
                .select_from(ActivityEvent)
                .where(ActivityEvent.user_id == uuid.UUID(account.user_id))
            )
            assert owner_events == 0
        assert len(list(services.storage.directory.iterdir())) == 1  # only the other user's file
        async with client_factory() as browser:
            assert (await login(browser, account.email, PASSWORD)).status_code == 401


class TestOverview:
    async def test_usage_stats_and_activity(
        self, account: Account, ready_session: ReadySession, services: Services
    ) -> None:
        await ready_session()
        await upload(account.client)

        usage = (await account.client.get("/api/v1/me/usage")).json()
        assert usage == {
            "plan": {
                "id": "trainer",
                "name": "Trainer",
                "monthly_price_cents": 4900,
                "monthly_session_limit": 10,
            },
            "sessions_this_month": 2,
            "remaining_this_month": 8,
        }
        stats = (await account.client.get("/api/v1/me/stats")).json()
        assert stats == {
            "total_sessions": 2,
            "quiz_questions": 3,
            "audio_seconds": 352,
            "sessions_this_month": 2,
        }
        activity = (await account.client.get("/api/v1/me/activity", params={"limit": 2})).json()
        assert [a["type"] for a in activity] == ["session_created", "session_created"]
        assert (
            await account.client.get("/api/v1/me/activity", params={"limit": 51})
        ).status_code == 422

    @pytest.mark.parametrize("settings_overrides", [{"default_plan": "pro"}])
    async def test_unlimited_plans_have_no_remaining_count(self, account: Account) -> None:
        usage = (await account.client.get("/api/v1/me/usage")).json()
        assert usage["plan"]["monthly_session_limit"] is None
        assert usage["remaining_this_month"] is None

    async def test_new_accounts_start_empty(self, account: Account, services: Services) -> None:
        stats = (await account.client.get("/api/v1/me/stats")).json()
        assert stats == {
            "total_sessions": 0,
            "quiz_questions": 0,
            "audio_seconds": 0,
            "sessions_this_month": 0,
        }
        user = await db_user(services, account.email)
        assert user.plan == "trainer"
        assert await activity_types(account) == [ActivityType.ACCOUNT_CREATED.value]
