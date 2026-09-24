from typing import Any

import pytest
from pydantic import ValidationError

from sonora.config import Settings
from sonora.plans import get_plan

PRODUCTION = {
    "environment": "production",
    "database_url": "postgresql+asyncpg://sonora:secret@db/sonora",
    "allowed_hosts": "sonora.example.com",
    "allowed_origins": "https://sonora.example.com",
}


def settings(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_lists_are_read_from_comma_separated_environment_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONORA_ALLOWED_ORIGINS", "https://a.example/, https://b.example")
    monkeypatch.setenv("SONORA_ALLOWED_HOSTS", "a.example,b.example")
    loaded = settings()
    assert loaded.allowed_origins == ["https://a.example", "https://b.example"]
    assert loaded.allowed_hosts == ["a.example", "b.example"]


def test_secrets_are_not_exposed_in_repr() -> None:
    loaded = settings(database_url="postgresql+asyncpg://u:hunter2@db/x")
    assert "hunter2" not in repr(loaded)


def test_valid_production_configuration() -> None:
    loaded = settings(**PRODUCTION)
    assert loaded.is_production
    assert loaded.docs_available is False
    assert loaded.session_cookie_name == "__Host-sonora_session"


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"allowed_hosts": "*"}, "ALLOWED_HOSTS"),
        ({"allowed_origins": ""}, "ALLOWED_ORIGINS"),
        ({"transcription_backend": "fake"}, "TRANSCRIPTION_BACKEND"),
        ({"database_url": "sqlite+aiosqlite:///x.db"}, "PostgreSQL"),
    ],
)
def test_unsafe_production_configurations_are_rejected(
    override: dict[str, Any], problem: str
) -> None:
    with pytest.raises(ValidationError, match=problem):
        settings(**{**PRODUCTION, **override})


def test_development_defaults_are_permissive_but_explicit() -> None:
    loaded = settings()
    assert loaded.docs_available is True
    assert settings(cookie_secure=False).session_cookie_name == "sonora_session"
    assert settings(docs_enabled=False).docs_available is False
    assert loaded.max_upload_bytes == 200 * 1024 * 1024
    assert loaded.max_json_body_bytes == 64 * 1024


def test_unknown_default_plan_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Unknown plan"):
        settings(default_plan="platinum")
    with pytest.raises(ValueError, match="Unknown plan"):
        get_plan("platinum")


def test_empty_whisper_language_means_auto_detect() -> None:
    assert settings(whisper_language="").whisper_language is None
