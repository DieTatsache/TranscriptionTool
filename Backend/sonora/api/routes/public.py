"""Unauthenticated endpoints for participants holding a share link."""

from typing import Annotated

from fastapi import APIRouter, Path

from sonora.api.deps import DB, rate_limit_ip
from sonora.api.schemas import (
    PublicShare,
    QuizCheckRequest,
    QuizQuestion,
    QuizResultOut,
    Script,
    TranscriptSegment,
)
from sonora.errors import NotFound
from sonora.models import ShareTab
from sonora.services import quiz as quiz_service
from sonora.services import shares as shares_service

router = APIRouter(prefix="/public", tags=["public"])

Token = Annotated[str, Path(min_length=1, max_length=128)]


@router.get(
    "/shares/{token}",
    response_model=PublicShare,
    dependencies=[rate_limit_ip("60/minute", "public-share")],
)
async def get_shared_session(token: Token, db: DB) -> PublicShare:
    link, session = await shares_service.resolve(db, token)
    tabs = set(link.tabs)
    return PublicShare(
        title=session.title,
        created_at=session.created_at,
        duration_seconds=session.duration_seconds,
        language=session.language,
        tabs=[ShareTab(t) for t in link.tabs],
        # Only what the trainer chose to share leaves the server.
        script=Script.model_validate(session.script)
        if ShareTab.SCRIPT in tabs and session.script
        else None,
        quiz=[QuizQuestion.model_validate(q) for q in quiz_service.public_questions(session.quiz)]
        if ShareTab.QUIZ in tabs and session.quiz
        else None,
        transcript=[TranscriptSegment.model_validate(s) for s in session.transcript]
        if ShareTab.TRANSCRIPT in tabs and session.transcript
        else None,
    )


@router.post(
    "/shares/{token}/quiz/check",
    response_model=QuizResultOut,
    dependencies=[rate_limit_ip("30/minute", "public-quiz")],
)
async def check_shared_quiz(token: Token, body: QuizCheckRequest, db: DB) -> QuizResultOut:
    link, session = await shares_service.resolve(db, token)
    if ShareTab.QUIZ not in link.tabs:
        raise NotFound("This link is invalid or has expired.", code="share_not_found")
    return QuizResultOut.model_validate(quiz_service.grade(session.quiz, body.answers))
