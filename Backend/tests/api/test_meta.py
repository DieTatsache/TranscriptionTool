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
    assert meta["share_tabs"] == ["script", "quiz", "transcript"]
    assert {"code": "de", "name": "German"} in meta["languages"]
