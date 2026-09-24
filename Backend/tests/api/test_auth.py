from datetime import timedelta
from typing import Any

import httpx
import pytest
from argon2 import PasswordHasher
from sqlalchemy import select, update

from sonora.container import Services
from sonora.db import utcnow
from sonora.models import AuthSession, User
from tests.conftest import PASSWORD, Account, register

COOKIE = "__Host-sonora_session"


def _set_cookie_header(response: httpx.Response) -> str:
    header = response.headers.get("set-cookie", "")
    assert header.startswith(COOKIE + "="), header
    return header.lower()


class TestRegister:
    async def test_creates_account_and_signs_in(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "  Marie   Tanner ", "email": "Marie@Example.COM", "password": PASSWORD},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == "marie@example.com"  # normalised
        assert body["user"]["name"] == "Marie Tanner"  # whitespace collapsed
        assert body["user"]["plan"] == "trainer"
        assert len(body["csrf_token"]) >= 40
        assert "password" not in response.text.lower().replace("password_", "")
        cookie = _set_cookie_header(response)
        for attribute in ("httponly", "secure", "samesite=strict", "path=/"):
            assert attribute in cookie
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["csrf_token"] == body["csrf_token"]

    async def test_stores_only_an_argon2_hash(
        self, client: httpx.AsyncClient, services: Services
    ) -> None:
        await register(client)
        async with services.sessionmaker() as db:
            user = await db.scalar(select(User))
        assert user is not None
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash

    async def test_rejects_duplicate_email_case_insensitively(
        self, client: httpx.AsyncClient
    ) -> None:
        await register(client, email="dup@example.com")
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "Other", "email": "DUP@example.com", "password": PASSWORD},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_taken"

    @pytest.mark.parametrize(
        ("password", "reason"),
        [
            ("short-pw", "at least 12"),
            ("aaaaaaaaaaaaaaaa", "too simple"),
            ("Password2024!!", "too common"),
            ("1234567890123", "easy to guess"),
            ("newtrainer-rocks-1", "email"),
        ],
    )
    async def test_rejects_weak_passwords(
        self, client: httpx.AsyncClient, password: str, reason: str
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "N", "email": "newtrainer@example.com", "password": password},
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "weak_password"
        assert reason in error["message"]

    async def test_validation_errors_never_echo_input(self, client: httpx.AsyncClient) -> None:
        secret = "super-secret-password-value"
        response = await client.post(
            "/api/v1/auth/register", json={"name": "N", "email": "not-an-email", "password": secret}
        )
        assert response.status_code == 422
        assert response.json()["error"]["details"][0]["field"] == "email"
        assert secret not in response.text

    @pytest.mark.parametrize("settings_overrides", [{"registration_enabled": False}])
    async def test_can_be_disabled(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "N", "email": "a@example.com", "password": PASSWORD},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "registration_disabled"

    async def test_is_rate_limited_per_ip(self, client: httpx.AsyncClient) -> None:
        payload: dict[str, Any] = {"name": "N", "password": "short"}
        for i in range(5):
            response = await client.post(
                "/api/v1/auth/register", json={**payload, "email": f"u{i}@example.com"}
            )
            assert response.status_code == 422
        response = await client.post(
            "/api/v1/auth/register", json={**payload, "email": "u9@example.com"}
        )
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0


class TestLogin:
    async def test_succeeds_with_correct_credentials(
        self, account: Account, client_factory: Any
    ) -> None:
        async with client_factory() as browser:
            response = await browser.post(
                "/api/v1/auth/login", json={"email": "TRAINER@example.com", "password": PASSWORD}
            )
            assert response.status_code == 200
            assert response.json()["user"]["email"] == account.email
            _set_cookie_header(response)
            assert (await browser.get("/api/v1/auth/me")).status_code == 200

    @pytest.mark.parametrize("email", ["trainer@example.com", "nobody@example.com"])
    async def test_failure_does_not_reveal_whether_the_account_exists(
        self, account: Account, client_factory: Any, email: str
    ) -> None:
        async with client_factory() as browser:
            response = await browser.post(
                "/api/v1/auth/login", json={"email": email, "password": "wrong-password-123"}
            )
        assert response.status_code == 401
        assert response.json()["error"] == {
            "code": "invalid_credentials",
            "message": "Invalid email or password.",
        }

    async def test_locks_an_email_after_repeated_failures(
        self, account: Account, client_factory: Any
    ) -> None:
        async with client_factory() as browser:
            for _ in range(5):
                bad = await browser.post(
                    "/api/v1/auth/login",
                    json={"email": account.email, "password": "nope-nope-nope"},
                )
                assert bad.status_code == 401
            locked = await browser.post(
                "/api/v1/auth/login", json={"email": account.email, "password": PASSWORD}
            )
            assert locked.status_code == 429
            assert locked.json()["error"]["code"] == "login_locked"
            assert int(locked.headers["retry-after"]) > 0
            # Other accounts are unaffected.
            other = await browser.post(
                "/api/v1/auth/login", json={"email": "unknown@example.com", "password": "x"}
            )
            assert other.status_code == 401

    async def test_success_resets_the_failure_counter(
        self, account: Account, client_factory: Any
    ) -> None:
        async with client_factory() as browser:
            for _ in range(4):
                await browser.post(
                    "/api/v1/auth/login", json={"email": account.email, "password": "bad"}
                )
            ok = await browser.post(
                "/api/v1/auth/login", json={"email": account.email, "password": PASSWORD}
            )
            assert ok.status_code == 200
            for _ in range(4):
                bad = await browser.post(
                    "/api/v1/auth/login", json={"email": account.email, "password": "bad"}
                )
                assert bad.status_code == 401

    async def test_replaces_the_previous_session_of_the_browser(
        self, account: Account, services: Services
    ) -> None:
        old_token = account.client.cookies[COOKIE]
        response = await account.client.post(
            "/api/v1/auth/login", json={"email": account.email, "password": PASSWORD}
        )
        assert response.status_code == 200
        assert account.client.cookies[COOKIE] != old_token
        async with services.sessionmaker() as db:
            assert len((await db.scalars(select(AuthSession))).all()) == 1

    async def test_rehashes_outdated_password_hashes(
        self, account: Account, services: Services, client_factory: Any
    ) -> None:
        # Simulate a hash created with different (older) parameters.
        old_hash = PasswordHasher(time_cost=1, memory_cost=16, parallelism=2).hash(PASSWORD)
        async with services.sessionmaker() as db:
            await db.execute(update(User).values(password_hash=old_hash))
            await db.commit()
        async with client_factory() as browser:
            ok = await browser.post(
                "/api/v1/auth/login", json={"email": account.email, "password": PASSWORD}
            )
        assert ok.status_code == 200
        async with services.sessionmaker() as db:
            new_hash = await db.scalar(select(User.password_hash))
        assert new_hash != old_hash
        assert new_hash is not None and "p=1" in new_hash


class TestSessionLifecycle:
    async def test_me_requires_a_session(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"

    async def test_logout_requires_csrf_token(self, account: Account) -> None:
        del account.client.headers["X-CSRF-Token"]
        response = await account.client.post("/api/v1/auth/logout")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_failed"

        account.client.headers["X-CSRF-Token"] = "forged-" + account.csrf
        assert (await account.client.post("/api/v1/auth/logout")).status_code == 403

    async def test_logout_ends_the_session(self, account: Account) -> None:
        token = account.client.cookies[COOKIE]
        response = await account.client.post("/api/v1/auth/logout")
        assert response.status_code == 204
        assert "max-age=0" in response.headers["set-cookie"].lower()
        # Even a replayed cookie is dead server-side.
        account.client.cookies.set(COOKIE, token)
        assert (await account.client.get("/api/v1/auth/me")).status_code == 401

    @pytest.mark.parametrize(
        "change",
        [
            {"expires_at": "past"},
            {"last_seen_at": "idle"},
        ],
    )
    async def test_expired_sessions_are_rejected_and_cleared(
        self, account: Account, services: Services, change: dict[str, str]
    ) -> None:
        now = utcnow()
        values = (
            {"expires_at": now - timedelta(seconds=1)}
            if "expires_at" in change
            else {
                "last_seen_at": now
                - timedelta(hours=services.settings.session_idle_hours, seconds=1)
            }
        )
        async with services.sessionmaker() as db:
            await db.execute(update(AuthSession).values(**values))
            await db.commit()

        response = await account.client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_expired"
        assert "max-age=0" in response.headers["set-cookie"].lower()
        async with services.sessionmaker() as db:
            assert (await db.scalars(select(AuthSession))).all() == []

    async def test_activity_refreshes_last_seen_but_not_on_every_request(
        self, account: Account, services: Services
    ) -> None:
        stale = utcnow() - timedelta(minutes=10)
        async with services.sessionmaker() as db:
            await db.execute(update(AuthSession).values(last_seen_at=stale))
            await db.commit()
        await account.client.get("/api/v1/auth/me")
        async with services.sessionmaker() as db:
            refreshed = await db.scalar(select(AuthSession.last_seen_at))
        assert refreshed is not None and refreshed > stale

    async def test_unknown_cookie_is_rejected(self, client: httpx.AsyncClient) -> None:
        client.cookies.set(COOKIE, "made-up-token")
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "session_expired"
