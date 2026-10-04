"""Listener feedback results for the session owner."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from sonora.api.deps import DB, OwnedSession
from sonora.api.schemas import (
    FeedbackCommentOut,
    FeedbackQuestionOut,
    FeedbackQuestionStatsOut,
    FeedbackSummaryOut,
)
from sonora.services import feedback as feedback_service

router = APIRouter(prefix="/sessions/{session_id}/feedback", tags=["feedback"])


@router.get("", response_model=FeedbackSummaryOut)
async def feedback_summary(session: OwnedSession, db: DB) -> FeedbackSummaryOut:
    summary = await feedback_service.summary(db, session)
    return FeedbackSummaryOut(
        responses=summary.responses,
        comments=summary.comments,
        questions=[
            FeedbackQuestionStatsOut(
                **FeedbackQuestionOut.of(stats.question).model_dump(),
                counts=stats.counts,
                answered=stats.answered,
                average=stats.average,
            )
            for stats in summary.questions
        ],
    )


@router.get("/comments", response_model=list[FeedbackCommentOut])
async def feedback_comments(
    session: OwnedSession,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> list[FeedbackCommentOut]:
    """Open answers, newest first."""
    rows = await feedback_service.comments(db, session, limit=limit, offset=offset)
    return [FeedbackCommentOut.model_validate(row) for row in rows]


@router.delete("/{response_id}", status_code=204)
async def delete_feedback(response_id: uuid.UUID, session: OwnedSession, db: DB) -> Response:
    """Removes one response, e.g. spam or a listener's request to delete their answer."""
    await feedback_service.delete_response(db, session, response_id)
    return Response(status_code=204)
