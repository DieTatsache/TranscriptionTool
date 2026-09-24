"""The worker loop: claims jobs, runs them with a lease heartbeat, retries with backoff.

Runs embedded in the API process for local development (``SONORA_WORKER_EMBEDDED``) or
standalone via ``python -m sonora.worker`` (the Docker ``worker`` service).
"""

import asyncio
import contextlib
import logging
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import delete, select, update

from sonora.ai.generation import GenerationError
from sonora.ai.llm import LLMError
from sonora.container import Services
from sonora.db import utcnow
from sonora.models import Job, JobStatus, JobType, SessionStatus, TrainingSession
from sonora.services import auth as auth_service
from sonora.worker import queue
from sonora.worker.pipeline import PermanentFailure, process_session

logger = logging.getLogger(__name__)

GENERIC_FAILURE = "Analysis failed. Please try again later."
INTERRUPTED_FAILURE = "Processing was interrupted. Please try again."
MAINTENANCE_INTERVAL_SECONDS = 600
FINISHED_JOB_RETENTION = timedelta(days=30)
ORPHAN_AUDIO_GRACE_SECONDS = 6 * 3600  # longer than any upload or job can take

Handler = Callable[[Services, Job], Awaitable[None]]
HANDLERS: dict[JobType, Handler] = {JobType.PROCESS_SESSION: process_session}


def retry_delay(attempt: int) -> timedelta:
    """30 s, 2 min, 8 min, ... capped at one hour."""
    return timedelta(seconds=min(30 * 4 ** max(0, attempt - 1), 3600))


class Worker:
    def __init__(self, services: Services, *, worker_id: str | None = None) -> None:
        self.services = services
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._last_maintenance = float("-inf")

    async def run(self, stop: asyncio.Event) -> None:
        logger.info("worker %s started", self.worker_id)
        while not stop.is_set():
            worked = False
            try:
                worked = await self.run_once()
                if time.monotonic() - self._last_maintenance >= MAINTENANCE_INTERVAL_SECONDS:
                    await self.maintenance()
            except Exception:
                # e.g. database briefly unavailable; keep the loop alive
                logger.exception("worker iteration failed")
            if not worked:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), self.services.settings.worker_poll_seconds)
        logger.info("worker %s stopped", self.worker_id)

    async def run_once(self) -> bool:
        """Claims and runs at most one job. Returns False when the queue was empty."""
        async with self.services.sessionmaker() as db:
            job = await queue.claim_next(
                db, self.worker_id, lease_seconds=self.services.settings.job_lease_seconds
            )
        if job is None:
            return False
        await self._execute(job)
        return True

    async def _execute(self, job: Job) -> None:
        logger.info("running job %s (%s, attempt %d)", job.id, job.type, job.attempts)
        heartbeat = asyncio.create_task(self._keep_lease(job))
        try:
            await HANDLERS[job.type](self.services, job)
        except PermanentFailure as exc:
            logger.warning("job %s failed permanently: %s", job.id, exc.user_message)
            await self._record_failure(job, exc.user_message, exc.user_message, retry=False)
        except (LLMError, GenerationError) as exc:
            logger.warning("job %s failed: %s", job.id, exc)
            await self._record_failure(job, repr(exc), GENERIC_FAILURE, retry=True)
        except Exception as exc:
            logger.exception("job %s crashed", job.id)
            await self._record_failure(job, repr(exc), GENERIC_FAILURE, retry=True)
        else:
            async with self.services.sessionmaker() as db:
                await queue.complete(db, job.id, self.worker_id)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _keep_lease(self, job: Job) -> None:
        lease = self.services.settings.job_lease_seconds
        while True:
            await asyncio.sleep(lease / 3)
            async with self.services.sessionmaker() as db:
                if not await queue.extend_lease(db, job.id, self.worker_id, lease_seconds=lease):
                    logger.info("lost lease on job %s (deleted or reclaimed)", job.id)
                    return

    async def _record_failure(
        self, job: Job, error: str, user_message: str, *, retry: bool
    ) -> None:
        async with self.services.sessionmaker() as db:
            will_retry = await queue.fail(
                db,
                job,
                self.worker_id,
                error,
                retry_in=retry_delay(job.attempts) if retry else None,
            )
            if job.session_id is not None:
                await db.execute(
                    update(TrainingSession)
                    .where(TrainingSession.id == job.session_id)
                    .values(
                        status=SessionStatus.QUEUED if will_retry else SessionStatus.FAILED,
                        error_message=None if will_retry else user_message,
                        updated_at=utcnow(),
                    )
                )
                await db.commit()

    async def maintenance(self) -> None:
        """Housekeeping: expired sign-ins, dead jobs, old job rows and orphaned audio."""
        self._last_maintenance = time.monotonic()
        services = self.services
        async with services.sessionmaker() as db:
            purged_sessions = await auth_service.purge_expired(db, services)

            abandoned = await queue.exhausted_abandoned_jobs(db)
            for job in abandoned:
                job.status = JobStatus.FAILED
                job.locked_by = job.locked_until = None
                job.finished_at = utcnow()
                job.last_error = "worker lost during last attempt"
            if abandoned:
                await db.execute(
                    update(TrainingSession)
                    .where(
                        TrainingSession.id.in_([j.session_id for j in abandoned if j.session_id])
                    )
                    .values(status=SessionStatus.FAILED, error_message=INTERRUPTED_FAILURE)
                )
            await db.execute(
                delete(Job).where(
                    Job.status.in_([JobStatus.SUCCEEDED, JobStatus.FAILED]),
                    Job.finished_at < utcnow() - FINISHED_JOB_RETENTION,
                )
            )
            await db.commit()
            keys = {
                key
                for key in await db.scalars(
                    select(TrainingSession.audio_key).where(TrainingSession.audio_key.is_not(None))
                )
                if key
            }
        removed = services.storage.delete_orphans(
            keys, older_than_seconds=ORPHAN_AUDIO_GRACE_SECONDS
        )
        logger.info(
            "maintenance: %d expired sign-ins, %d dead jobs, %d orphaned files removed",
            purged_sessions,
            len(abandoned),
            removed,
        )
