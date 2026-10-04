from typing import Any

import pytest
from pydantic import ValidationError

from sonora.config import Settings
from sonora.container import build_llm
from sonora.plans import (
    FREE_PLAN,
    NO_PLAN,
    PLANS,
    audio_limit_minutes,
    fallback_plan,
    get_plan,
    offered_plans,
    purchasable_plans,
)

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
    assert loaded.participant_cookie_name == "__Host-sonora_participant"


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"allowed_hosts": "*"}, "ALLOWED_HOSTS"),
        ({"allowed_origins": ""}, "ALLOWED_ORIGINS"),
        ({"transcription_backend": "fake"}, "TRANSCRIPTION_BACKEND"),
        ({"database_url": "sqlite+aiosqlite:///x.db"}, "PostgreSQL"),
        ({"rate_limit_enabled": False}, "RATE_LIMIT_ENABLED"),
        ({"database_echo": True}, "DATABASE_ECHO"),
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
    assert settings(cookie_secure=False).participant_cookie_name == "sonora_participant"
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


def test_llm_defaults_target_qwen35() -> None:
    loaded = settings()
    assert loaded.llm_model == "qwen3.5:9b"
    assert loaded.llm_context_tokens == 16384
    # Qwen3.5's recommended sampling for answers without reasoning.
    assert (loaded.llm_temperature, loaded.llm_top_p, loaded.llm_top_k) == (0.7, 0.8, 20)
    assert loaded.llm_presence_penalty == 1.5


async def test_the_llm_client_is_built_from_the_settings() -> None:
    llm = build_llm(
        settings(llm_model="qwen3.5:27b", llm_temperature=0.5, llm_top_k=40, llm_keep_alive="24h")
    )
    try:
        assert llm.model == "qwen3.5:27b"
        assert llm._keep_alive == "24h"
        assert llm._sampling.temperature == 0.5
        assert llm._sampling.top_k == 40
    finally:
        await llm.aclose()


@pytest.mark.parametrize(
    ("name", "value"),
    [("llm_top_p", 0), ("llm_top_p", 1.5), ("llm_top_k", 0), ("llm_presence_penalty", 3)],
)
def test_sampling_settings_are_bounded(name: str, value: float) -> None:
    with pytest.raises(ValidationError):
        settings(**{name: value})


def test_keep_alive_is_left_to_the_ollama_server_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert settings().llm_keep_alive is None
    monkeypatch.setenv("SONORA_LLM_KEEP_ALIVE", "")
    assert settings().llm_keep_alive is None


@pytest.mark.parametrize("value", ["10m", "24h", "1h30m", "1.5h", "-1m", "0", "3600", "-1"])
def test_keep_alive_accepts_what_ollama_understands(value: str) -> None:
    assert settings(llm_keep_alive=value).llm_keep_alive == value


@pytest.mark.parametrize("value", ["10 minutes", "forever", "5d", "1.5", "m"])
def test_keep_alive_rejects_values_ollama_would_refuse(value: str) -> None:
    # Caught at startup instead of failing every generation with HTTP 400.
    with pytest.raises(ValidationError):
        settings(llm_keep_alive=value)


def test_self_registered_accounts_start_on_the_free_plan() -> None:
    assert settings().default_plan == FREE_PLAN
    free = get_plan(FREE_PLAN)
    assert (free.monthly_price_cents, free.monthly_session_limit) == (0, 1)
    assert not free.purchasable  # switched to without payment, never sold
    assert get_plan(NO_PLAN).monthly_session_limit == 0
    assert [plan.id for plan in purchasable_plans()] == ["trainer", "pro"]
    assert "starter" not in PLANS  # became the free plan (migration 0003)


def test_the_free_plan_is_offered_only_as_the_default_plan() -> None:
    assert [plan.id for plan in offered_plans("free")] == ["free", "trainer", "pro"]
    assert [plan.id for plan in offered_plans("none")] == ["trainer", "pro"]
    assert [plan.id for plan in offered_plans("trainer")] == ["trainer", "pro"]
    assert fallback_plan("free") == FREE_PLAN
    assert fallback_plan("none") == NO_PLAN
    assert fallback_plan("pro") == NO_PLAN  # a closed beta's plan isn't kept after cancelling


def test_a_plan_never_allows_longer_recordings_than_the_server() -> None:
    assert audio_limit_minutes(PLANS["free"], 180) == 60
    assert audio_limit_minutes(PLANS["free"], 45) == 45
    assert audio_limit_minutes(PLANS["pro"], 180) == 180
