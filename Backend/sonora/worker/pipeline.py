"""Session processing jobs.

``process_session`` transcribes the audio (once), then generates the recap and quiz and
marks the session ready; in the same commit it queues ``analyze_session``, which writes
the lecture analysis. Each step commits its result, so a retry after a generation failure
reuses the transcript instead of transcribing again. A session deleted mid-way makes the
jobs stop quietly.

Every job type has a failure hook that records a failed attempt on what the job works on:
the session for processing, the analysis for analysing (a ready session stays ready).
"""

import asyncio
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from sqlalchemy.orm.exc import StaleDataError

from sonora.ai.analysis import LectureAnalyzer
from sonora.ai.generation import ContentGenerator
from sonora.container import Services
from sonora.db import utcnow
from sonora.models import (
    AnalysisStatus,
    Job,
    SessionAnalysis,
    SessionStatus,
    TrainingSession,
    User,
)
from sonora.plans import NO_PLAN, audio_limit_minutes, get_plan
from sonora.services import analysis as analysis_service
from sonora.services import quiz as quiz_service
from sonora.transcription import AudioTooLong, NoSpeechDetected, TranscriptionError

logger = logging.getLogger(__name__)


class PermanentFailure(Exception):
    """Retrying can't help. ``user_message`` is shown to the user."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


async def _save(db: AsyncSession) -> bool:
    """Commits; False if the row vanished (its session was deleted meanwhile)."""
    try:
        await db.commit()
    except StaleDataError:
        await db.rollback()
        return False
    return True


async def process_session(services: Services, job: Job) -> None:
    async with services.sessionmaker() as db:
        session = await db.get(
            TrainingSession, job.session_id, options=[undefer(TrainingSession.transcript)]
        )
        if session is None:
            logger.info("session of job %s no longer exists", job.id)
            return
        if session.transcript is None and not await _transcribe(db, services, session):
            return

        session.status = SessionStatus.GENERATING
        if not await _save(db):
            return
        generator = ContentGenerator(
            services.llm, context_tokens=services.settings.llm_context_tokens
        )
        content = await generator.generate(
            session.transcript or [],
            language=session.language,
            duration_seconds=session.duration_seconds,
        )
        session.script = content.script
        session.quiz = content.quiz
        session.quiz_count = len(content.quiz)
        if session.auto_title:
            session.title = content.title[:200]
        session.status = SessionStatus.READY
        session.ready_at = utcnow()
        session.error_message = None
        # No autoflush: if the session was deleted meanwhile, that must surface in _save.
        with db.no_autoflush:
            # Listener statistics belong to the previous quiz (defensive: only failed
            # sessions are processed again, and those were never shared).
            await quiz_service.discard_attempts(db, session)
            await analysis_service.enqueue(db, services, session.id)
        if await _save(db):
            logger.info("session %s ready (%d quiz questions)", session.id, session.quiz_count)


async def _transcribe(db: AsyncSession, services: Services, session: TrainingSession) -> bool:
    settings = services.settings
    session.status = SessionStatus.TRANSCRIBING
    if not await _save(db):
        return False
    audio_key = session.audio_key
    path = services.storage.path_for(audio_key) if audio_key else None
    if path is None or not path.is_file():
        raise PermanentFailure("The recording is no longer available. Please upload it again.")

    # The owner's current plan may allow less than the server (the free plan: 60 minutes).
    owner = await db.get(User, session.owner_id)
    plan = get_plan(owner.plan if owner else NO_PLAN)
    limit = audio_limit_minutes(plan, settings.max_audio_minutes)
    try:
        result = await asyncio.to_thread(
            services.transcriber.transcribe,
            path,
            language=session.language,
            max_duration_seconds=limit * 60,
        )
    except AudioTooLong as exc:
        by_plan = limit < settings.max_audio_minutes
        raise PermanentFailure(
            f"The recording is longer than the {limit}-minute limit"
            + (f" of the {plan.name} plan." if by_plan else ".")
        ) from exc
    except NoSpeechDetected as exc:
        raise PermanentFailure("No speech was detected in the recording.") from exc
    except TranscriptionError as exc:
        raise PermanentFailure(
            "The recording could not be decoded. Please upload a supported audio file."
        ) from exc

    session.transcript = [segment.to_dict() for segment in result.segments]
    session.duration_seconds = round(result.duration_seconds)
    session.language = session.language or result.language
    if not settings.keep_audio:
        session.audio_key = None  # data minimisation: audio is not needed after transcription
    if not await _save(db):
        return False
    if not settings.keep_audio:
        services.storage.delete(audio_key)
    logger.info("session %s transcribed (%d segments)", session.id, len(result.segments))
    return True


async def analyze_session(services: Services, job: Job) -> None:
    async with services.sessionmaker() as db:
        analysis = await db.get(SessionAnalysis, job.session_id)
        session = await db.get(
            TrainingSession, job.session_id, options=[undefer(TrainingSession.transcript)]
        )
        if analysis is None or session is None or not session.transcript:
            logger.info("nothing to analyse for job %s", job.id)
            return
        analysis.status = AnalysisStatus.RUNNING
        if not await _save(db):
            return
        analyzer = LectureAnalyzer(
            services.llm, context_tokens=services.settings.llm_context_tokens
        )
        result = await analyzer.analyze(session.transcript, language=session.language)
        analysis.result = result.to_dict()
        analysis.model = services.llm.model[:100]
        analysis.status = AnalysisStatus.READY
        analysis.error_message = None
        analysis.completed_at = utcnow()
        if await _save(db):
            logger.info("session %s analysed (%d topics)", session.id, len(result.topics))


async def session_failed(db: AsyncSession, job: Job, *, retrying: bool, message: str) -> None:
    """Failure hook of ``process_session`` (caller commits)."""
    await db.execute(
        update(TrainingSession)
        .where(TrainingSession.id == job.session_id)
        .values(
            status=SessionStatus.QUEUED if retrying else SessionStatus.FAILED,
            error_message=None if retrying else message,
            updated_at=utcnow(),
        )
    )


ANALYSIS_FAILURE = "The analysis could not be created. Please try again later."


async def analysis_failed(db: AsyncSession, job: Job, *, retrying: bool, message: str) -> None:
    """Failure hook of ``analyze_session`` (caller commits). Never touches the session."""
    del message  # technical details stay in the job; the user gets a generic reason
    await db.execute(
        update(SessionAnalysis)
        .where(SessionAnalysis.session_id == job.session_id)
        .values(
            status=AnalysisStatus.QUEUED if retrying else AnalysisStatus.FAILED,
            error_message=None if retrying else ANALYSIS_FAILURE,
            updated_at=utcnow(),
        )
    )
