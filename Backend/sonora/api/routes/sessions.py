import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from starlette.requests import ClientDisconnect

from sonora.api.deps import DB, CurrentUser, OwnedSessionWithContent, ServicesDep
from sonora.api.schemas import (
    Language,
    QuizCheckRequest,
    QuizQuestion,
    QuizResultOut,
    Script,
    SessionDetail,
    SessionSummary,
    Title,
    TranscriptSegment,
)
from sonora.errors import BadRequest
from sonora.services import quiz as quiz_service
from sonora.services import sessions as sessions_service

router = APIRouter(prefix="/sessions", tags=["sessions"])

_AUDIO_BODY = {
    "requestBody": {
        "required": True,
        "description": "Raw audio bytes (WebM, Ogg, MP3, M4A, WAV, FLAC or AAC). "
        "The format is detected from the content, not from Content-Type.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    user: CurrentUser,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SessionSummary]:
    rows = await sessions_service.list_for_owner(db, user, limit=limit, offset=offset)
    return [SessionSummary.model_validate(row) for row in rows]


@router.post("", status_code=202, response_model=SessionSummary, openapi_extra=_AUDIO_BODY)
async def upload_session(
    request: Request,
    user: CurrentUser,
    db: DB,
    services: ServicesDep,
    title: Annotated[Title | None, Query()] = None,
    language: Annotated[Language, Query()] = None,
) -> SessionSummary:
    """Accepts a recording as the raw request body and queues it for processing.

    A raw body (instead of multipart) lets authentication, CSRF, rate-limit and quota
    checks run before a single byte is accepted, and streams straight to storage.
    """
    try:
        session = await sessions_service.create_from_upload(
            db, services, user, audio=request.stream(), title=title or None, language=language
        )
    except ClientDisconnect:
        raise BadRequest("The upload was interrupted.", code="upload_interrupted") from None
    return SessionSummary.model_validate(session)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session: OwnedSessionWithContent) -> SessionDetail:
    return SessionDetail(
        **SessionSummary.model_validate(session).model_dump(),
        script=Script.model_validate(session.script) if session.script else None,
        quiz=[QuizQuestion.model_validate(q) for q in quiz_service.public_questions(session.quiz)]
        if session.quiz
        else None,
        transcript=[TranscriptSegment.model_validate(s) for s in session.transcript]
        if session.transcript
        else None,
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID, user: CurrentUser, db: DB, services: ServicesDep
) -> Response:
    await sessions_service.delete_owned(db, services, user, session_id)
    return Response(status_code=204)


@router.post("/{session_id}/retry", status_code=202, response_model=SessionSummary)
async def retry_session(
    session_id: uuid.UUID, user: CurrentUser, db: DB, services: ServicesDep
) -> SessionSummary:
    retried = await sessions_service.retry(db, services, user, session_id)
    return SessionSummary.model_validate(retried)


@router.post("/{session_id}/quiz/check", response_model=QuizResultOut)
async def check_quiz(body: QuizCheckRequest, session: OwnedSessionWithContent) -> QuizResultOut:
    return QuizResultOut.model_validate(quiz_service.grade(session.quiz, body.answers))
