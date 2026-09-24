"""Session processing: transcribe the audio (once), then generate the recap and quiz.

Each step commits its result, so a retry after a generation failure reuses the transcript
instead of transcribing again. A session deleted mid-way makes the pipeline stop quietly.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from sqlalchemy.orm.exc import StaleDataError

from sonora.ai.generation import ContentGenerator
from sonora.container import Services
from sonora.db import utcnow
from sonora.models import Job, SessionStatus, TrainingSession
from sonora.transcription import AudioTooLong, NoSpeechDetected, TranscriptionError

logger = logging.getLogger(__name__)


class PermanentFailure(Exception):
    """Retrying can't help. ``user_message`` is shown on the session."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


async def _save(db: AsyncSession) -> bool:
    """Commits; False if the session row vanished (deleted by its owner meanwhile)."""
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

    try:
        result = await asyncio.to_thread(
            services.transcriber.transcribe,
            path,
            language=session.language,
            max_duration_seconds=settings.max_audio_minutes * 60,
        )
    except AudioTooLong as exc:
        raise PermanentFailure(
            f"The recording is longer than the {settings.max_audio_minutes}-minute limit."
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
