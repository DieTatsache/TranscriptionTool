"""Runtime configuration.

Settings are read from environment variables prefixed with ``SONORA_`` (and from a
local ``.env`` file). Defaults target local development; combinations that are unsafe
in production are rejected at startup (see ``Settings._check_production``).
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from sonora.plans import get_plan


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class TranscriptionBackend(StrEnum):
    FASTER_WHISPER = "faster-whisper"
    # Dev/test only: returns a canned transcript without decoding audio.
    FAKE = "fake"


# Comma-separated in the environment, e.g. SONORA_ALLOWED_ORIGINS=https://a.example,https://b.example
CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SONORA_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"
    log_json: bool = False
    # None = enabled everywhere except production.
    docs_enabled: bool | None = None

    # --- Database ---------------------------------------------------------------------
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///./data/sonora.db")
    database_echo: bool = False

    # --- HTTP, cookies & sessions -------------------------------------------------------
    # Origins allowed to send state-changing requests (CSRF defence in depth).
    allowed_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    # Host header allow-list; "*" is only acceptable outside production.
    allowed_hosts: CsvList = Field(default_factory=lambda: ["*"])
    cookie_secure: bool = True
    session_ttl_hours: int = Field(default=14 * 24, ge=1)
    session_idle_hours: int = Field(default=72, ge=1)
    hsts_enabled: bool = False
    max_json_body_kb: int = Field(default=64, ge=1)

    # --- Accounts ---------------------------------------------------------------------
    registration_enabled: bool = True
    password_min_length: int = Field(default=12, ge=8, le=64)
    default_plan: str = "trainer"
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost_kib: int = Field(default=64 * 1024, ge=8)
    argon2_parallelism: int = Field(default=4, ge=1)
    login_max_failures: int = Field(default=5, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)

    # --- Rate limiting ----------------------------------------------------------------
    rate_limit_enabled: bool = True
    # memory:// is per process; use async+valkey://host:6379 when running several workers.
    rate_limit_storage_url: str = "memory://"

    # --- Uploads & storage ------------------------------------------------------------
    storage_dir: Path = Path("./data")
    max_upload_mb: int = Field(default=200, ge=1)
    max_audio_minutes: int = Field(default=180, ge=1)
    # Audio is deleted once transcribed unless this is set (data minimisation).
    keep_audio: bool = False

    # --- LLM (Ollama) -----------------------------------------------------------------
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2:3b"
    llm_context_tokens: int = Field(default=8192, ge=2048)
    llm_timeout_seconds: float = Field(default=600, gt=0)
    llm_temperature: float = Field(default=0.2, ge=0, le=2)
    llm_keep_alive: str = "10m"
    llm_max_concurrency: int = Field(default=2, ge=1)
    # Only sent when set; needed to switch off "thinking" on reasoning models.
    llm_think: bool | None = None

    # --- Transcription ----------------------------------------------------------------
    transcription_backend: TranscriptionBackend = TranscriptionBackend.FASTER_WHISPER
    # Model name (downloaded from Hugging Face on first use) or a local model directory.
    whisper_model: str = "small"
    whisper_model_dir: Path | None = None
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    whisper_beam_size: int = Field(default=5, ge=1)
    whisper_language: str | None = None
    whisper_cpu_threads: int = Field(default=0, ge=0)

    # --- Background worker ------------------------------------------------------------
    worker_embedded: bool = True
    worker_poll_seconds: float = Field(default=2.0, gt=0)
    job_max_attempts: int = Field(default=3, ge=1)
    job_lease_seconds: int = Field(default=300, ge=30)

    @field_validator("allowed_origins", "allowed_hosts", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("allowed_origins")
    @classmethod
    def _normalise_origins(cls, value: list[str]) -> list[str]:
        return [origin.rstrip("/") for origin in value]

    @field_validator("default_plan")
    @classmethod
    def _known_plan(cls, value: str) -> str:
        get_plan(value)
        return value

    @field_validator("whisper_language")
    @classmethod
    def _empty_language_is_auto(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _check_production(self) -> Self:
        if self.environment is not Environment.PRODUCTION:
            return self
        problems = []
        if not self.cookie_secure:
            problems.append("SONORA_COOKIE_SECURE must be true")
        if "*" in self.allowed_hosts:
            problems.append("SONORA_ALLOWED_HOSTS must list the public host names")
        if not self.allowed_origins:
            problems.append("SONORA_ALLOWED_ORIGINS must list the public origin")
        if self.transcription_backend is TranscriptionBackend.FAKE:
            problems.append("SONORA_TRANSCRIPTION_BACKEND=fake is for development only")
        if self.database_url.get_secret_value().startswith("sqlite"):
            problems.append("SONORA_DATABASE_URL must point to PostgreSQL")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def docs_available(self) -> bool:
        return self.docs_enabled if self.docs_enabled is not None else not self.is_production

    @property
    def session_cookie_name(self) -> str:
        # __Host- binds the cookie to this exact host (requires Secure, Path=/, no Domain).
        return "__Host-sonora_session" if self.cookie_secure else "sonora_session"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_json_body_bytes(self) -> int:
        return self.max_json_body_kb * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
