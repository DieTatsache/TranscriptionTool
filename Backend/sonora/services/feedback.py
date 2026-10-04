"""Anonymous listener feedback: submitted through share links, summarised for the owner.

Each listener (participant cookie, see ``sonora.security.participant_key``) can respond
once per session; the unique constraint enforces that under races too. A per-session cap
bounds what anonymous clients can store.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.db import rowcount
from sonora.errors import Conflict, NotFound, ValidationFailed
from sonora.feedback import FORM_VERSION, RATING_QUESTIONS, FeedbackQuestion
from sonora.models import FeedbackResponse, TrainingSession

MAX_RESPONSES_PER_SESSION = 5000


@dataclass(frozen=True, slots=True)
class QuestionStats:
    question: FeedbackQuestion
    # Responses per option index.
    counts: list[int]
    answered: int
    # Mean rating (option i = value i + 1) for stars and scales; None for choices.
    average: float | None


@dataclass(frozen=True, slots=True)
class FeedbackSummary:
    responses: int
    questions: list[QuestionStats]
    comments: int


def validate_ratings(ratings: Mapping[str, int]) -> dict[str, int]:
    if set(ratings) != {question.id for question in RATING_QUESTIONS}:
        raise ValidationFailed("Please answer every question.", code="feedback_incomplete")
    for question in RATING_QUESTIONS:
        if not 0 <= ratings[question.id] < len(question.options):
            raise ValidationFailed("An answer refers to an option that does not exist.")
    return {question.id: ratings[question.id] for question in RATING_QUESTIONS}


async def has_responded(db: AsyncSession, session_id: uuid.UUID, participant: str) -> bool:
    found = await db.scalar(
        select(FeedbackResponse.id).where(
            FeedbackResponse.session_id == session_id,
            FeedbackResponse.participant_key == participant,
        )
    )
    return found is not None


async def submit(
    db: AsyncSession,
    session: TrainingSession,
    participant: str,
    *,
    ratings: Mapping[str, int],
    comment: str | None,
) -> None:
    clean = validate_ratings(ratings)
    already = Conflict(
        "You have already given feedback on this session.", code="feedback_already_submitted"
    )
    if await has_responded(db, session.id, participant):
        raise already
    count = await db.scalar(
        select(func.count())
        .select_from(FeedbackResponse)
        .where(FeedbackResponse.session_id == session.id)
    )
    if (count or 0) >= MAX_RESPONSES_PER_SESSION:
        raise Conflict("This session doesn't accept more feedback.", code="feedback_closed")
    db.add(
        FeedbackResponse(
            session_id=session.id,
            participant_key=participant,
            form_version=FORM_VERSION,
            ratings=clean,
            comment=comment or None,
        )
    )
    try:
        await db.commit()
    except IntegrityError:  # a concurrent submission of the same listener won
        await db.rollback()
        raise already from None


async def summary(db: AsyncSession, session: TrainingSession) -> FeedbackSummary:
    rows = (
        await db.execute(
            select(FeedbackResponse.ratings, FeedbackResponse.comment).where(
                FeedbackResponse.session_id == session.id,
                FeedbackResponse.form_version == FORM_VERSION,
            )
        )
    ).all()
    stats = []
    for question in RATING_QUESTIONS:
        counts = [0] * len(question.options)
        for ratings, _comment in rows:
            value = ratings.get(question.id) if isinstance(ratings, dict) else None
            if isinstance(value, int) and 0 <= value < len(counts):
                counts[value] += 1
        answered = sum(counts)
        average = None
        if question.numeric and answered:
            average = round(sum((i + 1) * n for i, n in enumerate(counts)) / answered, 2)
        stats.append(QuestionStats(question, counts, answered, average))
    comments = await db.scalar(
        select(func.count())
        .select_from(FeedbackResponse)
        .where(FeedbackResponse.session_id == session.id, FeedbackResponse.comment.is_not(None))
    )
    return FeedbackSummary(responses=len(rows), questions=stats, comments=comments or 0)


async def comments(
    db: AsyncSession, session: TrainingSession, *, limit: int, offset: int
) -> list[FeedbackResponse]:
    rows = await db.scalars(
        select(FeedbackResponse)
        .where(FeedbackResponse.session_id == session.id, FeedbackResponse.comment.is_not(None))
        .order_by(FeedbackResponse.created_at.desc(), FeedbackResponse.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


async def delete_response(
    db: AsyncSession, session: TrainingSession, response_id: uuid.UUID
) -> None:
    """Removes one response (spam, abuse or a listener's erasure request)."""
    result = await db.execute(
        delete(FeedbackResponse).where(
            FeedbackResponse.id == response_id, FeedbackResponse.session_id == session.id
        )
    )
    if not rowcount(result):
        raise NotFound("Feedback not found.", code="feedback_not_found")
    await db.commit()
