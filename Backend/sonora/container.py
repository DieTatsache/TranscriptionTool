"""Process-wide service container shared by the API and the worker.

Built once at startup from ``Settings``. Tests build it with fakes for the LLM and the
transcriber instead of patching globals.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sonora.ai.llm import LLMClient, OllamaClient
from sonora.config import Settings
from sonora.db import create_engine, create_sessionmaker
from sonora.ratelimit import RateLimiter
from sonora.security import PasswordHasher
from sonora.storage import AudioStorage
from sonora.transcription import Transcriber, build_transcriber


@dataclass
class Services:
    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    passwords: PasswordHasher
    rate_limiter: RateLimiter
    storage: AudioStorage
    llm: LLMClient
    _transcriber: Transcriber | None = field(default=None, repr=False)

    @property
    def transcriber(self) -> Transcriber:
        # Created on first use: only the worker needs it (and its heavy imports).
        if self._transcriber is None:
            self._transcriber = build_transcriber(self.settings)
        return self._transcriber

    async def aclose(self) -> None:
        await self.llm.aclose()
        await self.engine.dispose()


def build_services(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    transcriber: Transcriber | None = None,
) -> Services:
    engine = create_engine(settings.database_url.get_secret_value(), echo=settings.database_echo)
    return Services(
        settings=settings,
        engine=engine,
        sessionmaker=create_sessionmaker(engine),
        passwords=PasswordHasher(
            time_cost=settings.argon2_time_cost,
            memory_cost_kib=settings.argon2_memory_cost_kib,
            parallelism=settings.argon2_parallelism,
        ),
        rate_limiter=RateLimiter(
            settings.rate_limit_storage_url, enabled=settings.rate_limit_enabled
        ),
        storage=AudioStorage(settings.storage_dir),
        llm=llm
        or OllamaClient(
            settings.llm_base_url,
            settings.llm_model,
            context_tokens=settings.llm_context_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            keep_alive=settings.llm_keep_alive,
            max_concurrency=settings.llm_max_concurrency,
            think=settings.llm_think,
        ),
        _transcriber=transcriber,
    )
