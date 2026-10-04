import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sonora import __version__


async def test_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.json() == {"status": "ok"}


async def test_readiness_checks_the_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200


async def test_readiness_reports_database_outage(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*_: object, **__: object) -> None:
        raise ConnectionError("database down")

    monkeypatch.setattr(AsyncSession, "execute", broken)
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


@pytest.mark.parametrize(
    "settings_overrides",
    [{"registration_enabled": False, "max_upload_mb": 50, "password_min_length": 14}],
)
async def test_meta_exposes_client_configuration(client: httpx.AsyncClient) -> None:
    meta = (await client.get("/api/v1/meta")).json()
    assert meta["version"] == __version__
    assert meta["registration_enabled"] is False
    assert meta["max_upload_mb"] == 50
    assert meta["password_min_length"] == 14
    assert meta["max_audio_minutes"] == 180
    assert meta["share_tabs"] == ["script", "quiz", "chat", "transcript", "feedback"]
    assert {"code": "de", "name": "German"} in meta["languages"]
    # The plans on offer: the free tier, then those sold at the prices the checkout charges.
    assert meta["plans"] == [
        {
            "id": "free",
            "name": "Free",
            "monthly_price_cents": 0,
            "monthly_session_limit": 1,
            "max_audio_minutes": 60,
            "purchasable": False,
        },
        {
            "id": "trainer",
            "name": "Trainer",
            "monthly_price_cents": 4900,
            "monthly_session_limit": 10,
            "max_audio_minutes": None,
            "purchasable": True,
        },
        {
            "id": "pro",
            "name": "Pro",
            "monthly_price_cents": 9900,
            "monthly_session_limit": None,
            "max_audio_minutes": None,
            "purchasable": True,
        },
    ]
    assert meta["billing_provider"] == "mock"


@pytest.mark.parametrize("settings_overrides", [{"default_plan": "none"}])
async def test_meta_offers_no_free_plan_without_a_free_tier(client: httpx.AsyncClient) -> None:
    meta = (await client.get("/api/v1/meta")).json()
    assert [plan["id"] for plan in meta["plans"]] == ["trainer", "pro"]
