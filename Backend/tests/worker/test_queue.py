import asyncio
import uuid
from datetime import timedelta

from sqlalchemy import update

from sonora.container import Services
from sonora.db import utcnow
from sonora.models import Job, JobStatus, JobType, SessionStatus, TrainingSession, User
from sonora.worker import queue

LEASE = 60


async def make_job(services: Services, *, max_attempts: int = 3) -> uuid.UUID:
    async with services.sessionmaker() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"{uuid.uuid4().hex}@x.io",
            name="U",
            password_hash="-",
            plan="pro",
        )
        session = TrainingSession(
            id=uuid.uuid4(), owner_id=user.id, title="T", status=SessionStatus.QUEUED
        )
        db.add_all([user, session])
        job = queue.enqueue(db, JobType.PROCESS_SESSION, session.id, max_attempts=max_attempts)
        await db.commit()
        return job.id


async def claim(services: Services, worker: str = "w1") -> Job | None:
    async with services.sessionmaker() as db:
        return await queue.claim_next(db, worker, lease_seconds=LEASE)


async def set_job(services: Services, job_id: uuid.UUID, **values: object) -> None:
    async with services.sessionmaker() as db:
        await db.execute(update(Job).where(Job.id == job_id).values(**values))
        await db.commit()


async def get_job(services: Services, job_id: uuid.UUID) -> Job:
    async with services.sessionmaker() as db:
        job = await db.get(Job, job_id)
        assert job is not None
        return job


async def test_claim_takes_a_lease_and_counts_the_attempt(services: Services) -> None:
    job_id = await make_job(services)

    job = await claim(services)

    assert job is not None and job.id == job_id
    assert job.status is JobStatus.RUNNING
    assert job.locked_by == "w1"
    assert job.attempts == 1
    assert job.locked_until is not None and job.locked_until > utcnow() + timedelta(
        seconds=LEASE - 5
    )
    assert await claim(services, "w2") is None  # not claimable twice


async def test_concurrent_workers_never_share_a_job(services: Services) -> None:
    await make_job(services)
    results = await asyncio.gather(*(claim(services, f"w{i}") for i in range(4)))
    assert sum(job is not None for job in results) == 1


async def test_future_jobs_wait_until_due(services: Services) -> None:
    job_id = await make_job(services)
    await set_job(services, job_id, run_after=utcnow() + timedelta(minutes=5))
    assert await claim(services) is None
    await set_job(services, job_id, run_after=utcnow() - timedelta(seconds=1))
    assert await claim(services) is not None


async def test_abandoned_jobs_are_reclaimed_after_the_lease(services: Services) -> None:
    job_id = await make_job(services)
    await claim(services, "crashed")
    await set_job(services, job_id, locked_until=utcnow() - timedelta(seconds=1))

    job = await claim(services, "w2")

    assert job is not None
    assert job.locked_by == "w2"
    assert job.attempts == 2


async def test_exhausted_jobs_are_not_claimed(services: Services) -> None:
    job_id = await make_job(services, max_attempts=1)
    await claim(services, "crashed")
    await set_job(services, job_id, locked_until=utcnow() - timedelta(seconds=1))
    assert await claim(services, "w2") is None
    async with services.sessionmaker() as db:
        abandoned = await queue.exhausted_abandoned_jobs(db)
    assert [job.id for job in abandoned] == [job_id]


async def test_extend_lease_only_for_the_owner(services: Services) -> None:
    job_id = await make_job(services)
    await claim(services, "w1")
    async with services.sessionmaker() as db:
        assert await queue.extend_lease(db, job_id, "w1", lease_seconds=600)
        assert not await queue.extend_lease(db, job_id, "intruder", lease_seconds=600)
    job = await get_job(services, job_id)
    assert job.locked_until is not None and job.locked_until > utcnow() + timedelta(seconds=500)


async def test_complete(services: Services) -> None:
    job_id = await make_job(services)
    await claim(services)
    async with services.sessionmaker() as db:
        await queue.complete(db, job_id, "w1")
    job = await get_job(services, job_id)
    assert job.status is JobStatus.SUCCEEDED
    assert job.locked_by is None
    assert job.finished_at is not None


async def test_fail_with_retry_reschedules(services: Services) -> None:
    job_id = await make_job(services)
    job = await claim(services)
    assert job is not None
    async with services.sessionmaker() as db:
        retried = await queue.fail(db, job, "w1", "boom", retry_in=timedelta(minutes=2))
    assert retried
    stored = await get_job(services, job_id)
    assert stored.status is JobStatus.PENDING
    assert stored.run_after > utcnow() + timedelta(seconds=100)
    assert stored.last_error == "boom"
    assert stored.locked_by is None


async def test_fail_is_final_without_retry_or_attempts_left(services: Services) -> None:
    for retry_in, max_attempts in ((None, 3), (timedelta(seconds=1), 1)):
        job_id = await make_job(services, max_attempts=max_attempts)
        job = await claim(services)
        assert job is not None
        async with services.sessionmaker() as db:
            assert not await queue.fail(db, job, "w1", "x" * 5000, retry_in=retry_in)
        stored = await get_job(services, job_id)
        assert stored.status is JobStatus.FAILED
        assert stored.finished_at is not None
        assert stored.last_error is not None and len(stored.last_error) == 2000
