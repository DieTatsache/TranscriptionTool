"""Training sessions: upload, listing, retrieval, deletion and retry."""

import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from sonora.container import Services
from sonora.db import utcnow
from sonora.errors import Conflict, NotFound, PermissionDenied
from sonora.models import ActivityType, JobType, SessionStatus, TrainingSession, User
from sonora.plans import get_plan
from sonora.services import activity
from sonora.worker import queue

logger = logging.getLogger(__name__)

UPLOADS_PER_HOUR = "10/hour"
CONTENT_COLUMNS = (TrainingSession.transcript, TrainingSession.script, TrainingSession.quiz)


def placeholder_title(now: datetime) -> str:
    return f"New session — {now.strftime('%b')} {now.day}, {now.year}"


async def list_for_owner(
    db: AsyncSession, owner: User, *, limit: int, offset: int
) -> Sequence[TrainingSession]:
    rows = await db.scalars(
        select(TrainingSession)
        .where(TrainingSession.owner_id == owner.id)
        .order_by(TrainingSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return rows.all()


async def get_owned(
    db: AsyncSession, owner: User, session_id: uuid.UUID, *, with_content: bool = False
) -> TrainingSession:
    """404 for missing *and* foreign sessions, so ids can't be probed."""
    query = select(TrainingSession).where(
        TrainingSession.id == session_id, TrainingSession.owner_id == owner.id
    )
    if with_content:
        query = query.options(*(undefer(column) for column in CONTENT_COLUMNS))
    session = await db.scalar(query)
    if session is None:
        raise NotFound("Session not found.", code="session_not_found")
    return session


async def _ensure_quota(db: AsyncSession, owner: User) -> None:
    remaining = await activity.remaining_sessions(db, owner)
    if remaining == 0:
        plan = get_plan(owner.plan)
        raise PermissionDenied(
            f"You have used all {plan.monthly_session_limit} sessions of your {plan.name} plan "
            "this month.",
            code="quota_exceeded",
        )


async def create_from_upload(
    db: AsyncSession,
    services: Services,
    owner: User,
    *,
    audio: AsyncIterator[bytes],
    title: str | None,
    language: str | None,
) -> TrainingSession:
    await services.rate_limiter.hit(
        UPLOADS_PER_HOUR, "upload", str(owner.id), message="Too many uploads. Please wait a bit."
    )
    await _ensure_quota(db, owner)  # cheap early check before accepting any bytes
    # End the read transaction so none is held open while the upload streams in
    # (commit, unlike rollback, keeps loaded objects usable).
    await db.commit()

    stored = await services.storage.save_stream(audio, max_bytes=services.settings.max_upload_bytes)
    try:
        # Lock the owner row so concurrent uploads can't both pass the quota check.
        await db.execute(select(User.id).where(User.id == owner.id).with_for_update())
        await _ensure_quota(db, owner)
        now = utcnow()
        session = TrainingSession(
            id=uuid.uuid4(),
            owner_id=owner.id,
            title=title or placeholder_title(now),
            auto_title=title is None,
            status=SessionStatus.QUEUED,
            language=language,
            audio_key=stored.key,
            audio_mime=stored.format.mime,
            audio_size_bytes=stored.size,
        )
        db.add(session)
        await db.flush()
        queue.enqueue(
            db, JobType.PROCESS_SESSION, session.id, max_attempts=services.settings.job_max_attempts
        )
        activity.record(db, owner.id, ActivityType.SESSION_CREATED, session.title)
        await db.commit()
    except BaseException:
        await db.rollback()
        services.storage.delete(stored.key)
        raise
    logger.info("session %s queued (%d bytes, %s)", session.id, stored.size, stored.format.mime)
    return session


async def delete_owned(
    db: AsyncSession, services: Services, owner: User, session_id: uuid.UUID
) -> None:
    session = await get_owned(db, owner, session_id)
    audio_key, title = session.audio_key, session.title
    # Shares, chat messages and jobs cascade in the database.
    await db.execute(delete(TrainingSession).where(TrainingSession.id == session.id))
    activity.record(db, owner.id, ActivityType.SESSION_DELETED, title)
    await db.commit()
    services.storage.delete(audio_key)


async def retry(
    db: AsyncSession, services: Services, owner: User, session_id: uuid.UUID
) -> TrainingSession:
    """Re-queues a failed session. Transcripts are reused; audio must still exist otherwise."""
    session = await get_owned(db, owner, session_id, with_content=True)
    if session.status is not SessionStatus.FAILED:
        raise Conflict("Only failed sessions can be retried.", code="not_retryable")
    if session.transcript is None and session.audio_key is None:
        raise Conflict(
            "The recording is no longer available; please upload it again.", code="not_retryable"
        )
    session.status = SessionStatus.QUEUED
    session.error_message = None
    queue.enqueue(
        db, JobType.PROCESS_SESSION, session.id, max_attempts=services.settings.job_max_attempts
    )
    await db.commit()
    return session
