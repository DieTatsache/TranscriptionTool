"""Lecture analysis state for session owners.

New sessions get their analysis queued automatically once they are ready (see the worker
pipeline). Sessions without one (created before the feature, or whose analysis failed)
can request it; a finished analysis is not regenerated.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sonora.container import Services
from sonora.errors import Conflict
from sonora.models import (
    AnalysisStatus,
    JobType,
    SessionAnalysis,
    SessionStatus,
    TrainingSession,
    User,
)
from sonora.worker import queue

REQUESTS_PER_HOUR = "10/hour"  # per user: each analysis costs several LLM calls


async def get(db: AsyncSession, session: TrainingSession) -> SessionAnalysis | None:
    return await db.get(SessionAnalysis, session.id, populate_existing=True)


async def enqueue(db: AsyncSession, services: Services, session_id: uuid.UUID) -> SessionAnalysis:
    """Queues an analysis job in the caller's transaction (resets a failed analysis)."""
    analysis = await db.get(SessionAnalysis, session_id)
    if analysis is None:
        analysis = SessionAnalysis(session_id=session_id, status=AnalysisStatus.QUEUED)
        db.add(analysis)
    else:
        analysis.status = AnalysisStatus.QUEUED
        analysis.error_message = None
        analysis.result = None
        analysis.completed_at = None
    queue.enqueue(
        db, JobType.ANALYZE_SESSION, session_id, max_attempts=services.settings.job_max_attempts
    )
    return analysis


async def request(
    db: AsyncSession, services: Services, owner: User, session: TrainingSession
) -> SessionAnalysis:
    await services.rate_limiter.hit(
        REQUESTS_PER_HOUR,
        "analysis",
        str(owner.id),
        message="Too many analysis requests. Please try again later.",
    )
    if session.status is not SessionStatus.READY:
        raise Conflict("The session is still being processed.", code="session_not_ready")
    current = await get(db, session)
    if current is not None and current.status is AnalysisStatus.READY:
        raise Conflict("The analysis is already available.", code="analysis_exists")
    if current is not None and current.status in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING):
        return current  # already on its way
    analysis = await enqueue(db, services, session.id)
    await db.commit()
    return analysis
