"""Cross-cutting HTTP protections: headers, origins, hosts, body limits, error envelope."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from sonora.container import build_services
from sonora.main import create_app
from tests.conftest import BASE_URL, Account, make_settings
from tests.fakes import FakeLLM, FakeTranscriber


class TestSecurityHeaders:
    async def test_are_set_on_every_response(self, client: httpx.AsyncClient) -> None:
        for response in (await client.get("/api/v1/meta"), await client.get("/api/v1/nope")):
            headers = response.headers
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["x-frame-options"] == "DENY"
            assert headers["referrer-policy"] == "no-referrer"
            assert headers["cache-control"] == "no-store"
            assert "default-src 'none'" in headers["content-security-policy"]
            assert "frame-ancestors 'none'" in headers["content-security-policy"]
            assert "strict-transport-security" not in headers

    @pytest.mark.parametrize("settings_overrides", [{"hsts_enabled": True}])
    async def test_hsts_when_enabled(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/meta")
        assert response.headers["strict-transport-security"].startswith("max-age=63072000")

    async def test_request_id_is_echoed_only_when_well_formed(
        self, client: httpx.AsyncClient
    ) -> None:
        good = await client.get("/api/v1/meta", headers={"X-Request-ID": "trace-123"})
        assert good.headers["x-request-id"] == "trace-123"
        bad = await client.get(
            "/api/v1/meta", headers={"X-Request-ID": "<script>alert(1)</script>"}
        )
        assert bad.headers["x-request-id"] != "<script>alert(1)</script>"
        assert len(bad.headers["x-request-id"]) == 32


class TestOriginCheck:
    async def test_blocks_state_changes_from_foreign_origins(self, account: Account) -> None:
        response = await account.client.post(
            "/api/v1/auth/logout", headers={"Origin": "https://evil.example"}
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_not_allowed"
        assert (await account.client.get("/api/v1/auth/me")).status_code == 200

    async def test_blocks_null_origin(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/api/v1/auth/login", json={}, headers={"Origin": "null"})
        assert response.status_code == 403

    @pytest.mark.parametrize("origin", ["https://app.example", "https://testserver"])
    async def test_allows_configured_and_same_origin(
        self, client: httpx.AsyncClient, origin: str
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "a@b.c", "password": "x"},
            headers={"Origin": origin},
        )
        assert response.status_code == 401  # reached the endpoint

    async def test_safe_methods_are_not_checked(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/meta", headers={"Origin": "https://evil.example"})
        assert response.status_code == 200


class TestHostAndBodyLimits:
    async def test_rejects_unknown_host_headers(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/meta", headers={"Host": "evil.example"})
        assert response.status_code == 400

    async def test_rejects_oversized_json_by_content_length(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            content=b"{" + b" " * (64 * 1024) + b"}",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"

    async def test_rejects_oversized_streamed_json(self, client: httpx.AsyncClient) -> None:
        async def body() -> AsyncIterator[bytes]:
            for _ in range(80):
                yield b" " * 1024

        response = await client.post(
            "/api/v1/auth/login", content=body(), headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413

    async def test_rejects_malformed_content_length(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login", content=b"{}", headers={"Content-Length": "abc"}
        )
        assert response.status_code == 400

    async def test_json_endpoints_require_a_json_content_type(
        self, client: httpx.AsyncClient
    ) -> None:
        # Blocks "simple" cross-site form posts (text/plain) from reaching JSON endpoints.
        response = await client.post(
            "/api/v1/auth/login",
            content=b'{"email": "a@b.c", "password": "x"}',
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 422


class TestErrorEnvelope:
    async def test_unknown_route(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/does-not-exist")
        assert response.status_code == 404
        assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}

    async def test_wrong_method(self, client: httpx.AsyncClient) -> None:
        response = await client.put("/api/v1/meta")
        assert response.status_code == 405
        assert response.json()["error"]["code"] == "method_not_allowed"

    async def test_crashes_become_generic_500_with_headers(self, app: FastAPI) -> None:
        @app.get("/api/v1/_boom")
        async def boom() -> None:
            raise RuntimeError("database password is hunter2")

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as c:
            response = await c.get("/api/v1/_boom")
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "hunter2" not in response.text
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-request-id"]


class TestDocs:
    async def test_available_outside_production(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/api/v1/openapi.json")).status_code == 200
        docs = await client.get("/api/v1/docs")
        assert docs.status_code == 200
        assert "content-security-policy" not in docs.headers  # Swagger UI loads CDN assets

    async def test_disabled_in_production(self, tmp_path: Path) -> None:
        settings = make_settings(
            tmp_path,
            environment="production",
            database_url="postgresql+asyncpg://sonora:secret@db/sonora",
            transcription_backend="faster-whisper",
        )
        # The PostgreSQL engine connects lazily; these requests never touch the database.
        services = build_services(settings, llm=FakeLLM(), transcriber=FakeTranscriber())
        app = create_app(settings, services=services)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=BASE_URL
            ) as c:
                assert (await c.get("/api/v1/openapi.json")).status_code == 404
                assert (await c.get("/api/v1/docs")).status_code == 404
        finally:
            await services.aclose()


def test_fakes_satisfy_protocols() -> None:
    # Keeps the test doubles honest when the protocols change.
    from sonora.ai.llm import LLMClient
    from sonora.transcription import Transcriber

    llm: LLMClient = FakeLLM()
    transcriber: Transcriber = FakeTranscriber()
    assert llm and transcriber
