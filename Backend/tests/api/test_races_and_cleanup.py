"""Concurrency safety nets: unique constraints under races, cleanup of partial uploads."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from sonora.container import Services
from sonora.services import activity
from sonora.services import auth as auth_service
from tests.conftest import PASSWORD, Account, register, upload


@pytest.fixture
def lost_email_race(monkeypatch: pytest.MonkeyPatch) -> None:
    """The friendly uniqueness pre-check passes, as if a concurrent request won the race."""

    async def never_in_use(*_: Any) -> bool:
        return False

    monkeypatch.setattr(auth_service, "email_in_use", never_in_use)


@pytest.mark.usefixtures("lost_email_race")
async def test_registration_race_is_caught_by_the_unique_constraint(
    client: httpx.AsyncClient, client_factory: Any
) -> None:
    await register(client, email="race@example.com")
    async with client_factory() as other:
        response = await other.post(
            "/api/v1/auth/register",
            json={"name": "Second", "email": "race@example.com", "password": PASSWORD},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.usefixtures("lost_email_race")
async def test_email_change_race_is_caught_by_the_unique_constraint(
    account: Account, other_account: Account
) -> None:
    response = await account.client.patch(
        "/api/v1/me", json={"email": other_account.email, "current_password": PASSWORD}
    )
    assert response.status_code == 409
    assert (await account.client.get("/api/v1/auth/me")).json()["user"]["email"] == account.email


async def test_quota_is_rechecked_after_the_upload_and_the_file_removed(
    account: Account, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another upload used the last slot while this one was streaming.
    remaining: Iterator[int] = iter([1, 0])

    async def racing_remaining(*_: Any) -> int:
        return next(remaining)

    monkeypatch.setattr(activity, "remaining_sessions", racing_remaining)
    response = await upload(account.client)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "quota_exceeded"
    assert list(services.storage.directory.iterdir()) == []


async def test_client_disconnect_mid_upload_leaves_nothing_behind(
    app: FastAPI, account: Account, services: Services
) -> None:
    cookie = "; ".join(f"{name}={value}" for name, value in account.client.cookies.items())
    messages = iter(
        [
            {
                "type": "http.request",
                "body": b"\x1a\x45\xdf\xa3" + b"\x00" * 4096,
                "more_body": True,
            },
            {"type": "http.disconnect"},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return next(messages)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/v1/sessions",
        "raw_path": b"/api/v1/sessions",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"cookie", cookie.encode()),
            (b"x-csrf-token", account.csrf.encode()),
            (b"content-type", b"audio/webm"),
        ],
        "client": ("127.0.0.1", 5000),
        "server": ("testserver", 443),
    }
    await app(scope, receive, send)

    assert sent[0]["status"] == 400
    assert list(services.storage.directory.iterdir()) == []
