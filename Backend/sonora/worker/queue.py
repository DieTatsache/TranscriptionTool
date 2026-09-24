"""Job queue operations.

Claiming is an optimistic ``UPDATE ... WHERE id = :id AND <still claimable>``: whichever
worker's update matches the row wins, so no two workers run the same job, on SQLite and
PostgreSQL alike. Running jobs hold a lease that the worker keeps extending; when a
worker dies, the lease expires and the job becomes claimable again.
"""

import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from sonora.db import rowcount, utcnow
from sonora.models import Job, JobStatus, JobType


def enqueue(
    db: AsyncSession, job_type: JobType, session_id: uuid.UUID, *, max_attempts: int
) -> Job:
    """Adds a job to the caller's transaction."""
    job = Job(
        type=job_type,
        session_id=session_id,
        status=JobStatus.PENDING,
        max_attempts=max_attempts,
        run_after=utcnow(),
    )
    db.add(job)
    return job


def _claimable() -> ColumnElement[bool]:
    now = utcnow()
    return and_(
        Job.attempts < Job.max_attempts,
        or_(
            and_(Job.status == JobStatus.PENDING, Job.run_after <= now),
            and_(Job.status == JobStatus.RUNNING, Job.locked_until < now),  # abandoned
        ),
    )


async def claim_next(db: AsyncSession, worker_id: str, *, lease_seconds: int) -> Job | None:
    candidates = list(
        await db.scalars(select(Job.id).where(_claimable()).order_by(Job.run_after).limit(5))
    )
    for job_id in candidates:
        now = utcnow()
        result = await db.execute(
            update(Job)
            .where(Job.id == job_id, _claimable())
            .values(
                status=JobStatus.RUNNING,
                locked_by=worker_id,
                locked_until=now + timedelta(seconds=lease_seconds),
                attempts=Job.attempts + 1,
                updated_at=now,
            )
        )
        await db.commit()
        if rowcount(result) == 1:
            return await db.get(Job, job_id, populate_existing=True)
    return None


async def extend_lease(
    db: AsyncSession, job_id: uuid.UUID, worker_id: str, *, lease_seconds: int
) -> bool:
    """False if the job is no longer ours (lease lost or job deleted with its session)."""
    result = await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id, Job.status == JobStatus.RUNNING)
        .values(locked_until=utcnow() + timedelta(seconds=lease_seconds))
    )
    await db.commit()
    return rowcount(result) == 1


async def complete(db: AsyncSession, job_id: uuid.UUID, worker_id: str) -> None:
    await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id)
        .values(status=JobStatus.SUCCEEDED, locked_by=None, locked_until=None, finished_at=utcnow())
    )
    await db.commit()


async def fail(
    db: AsyncSession,
    job: Job,
    worker_id: str,
    error: str,
    *,
    retry_in: timedelta | None,
) -> bool:
    """Records a failure. Returns True if the job will be retried."""
    retry = retry_in is not None and job.attempts < job.max_attempts
    values: dict[str, object] = {
        "locked_by": None,
        "locked_until": None,
        "last_error": error[:2000],
    }
    if retry and retry_in is not None:
        values |= {"status": JobStatus.PENDING, "run_after": utcnow() + retry_in}
    else:
        values |= {"status": JobStatus.FAILED, "finished_at": utcnow()}
    await db.execute(update(Job).where(Job.id == job.id, Job.locked_by == worker_id).values(values))
    await db.commit()
    return retry


async def exhausted_abandoned_jobs(db: AsyncSession) -> list[Job]:
    """Running jobs whose worker died after the last allowed attempt."""
    rows = await db.scalars(
        select(Job).where(
            Job.status == JobStatus.RUNNING,
            Job.locked_until < utcnow(),
            Job.attempts >= Job.max_attempts,
        )
    )
    return list(rows)
