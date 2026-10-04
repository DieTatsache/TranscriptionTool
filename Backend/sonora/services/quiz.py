"""Quiz presentation, server-side grading and listener statistics.

Correct answers never leave the server before an attempt is submitted, so participants
can't read them from the network tab. Each listener's first graded attempt on a shared
quiz is stored anonymously, which gives the owner per-question answer statistics.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.errors import Conflict, ValidationFailed
from sonora.models import QuizAttempt, TrainingSession

MAX_RECORDED_ATTEMPTS = 5000  # per session; bounds what anonymous clients can store


@dataclass(frozen=True, slots=True)
class QuestionResult:
    selected: int | None
    correct_option: int
    is_correct: bool
    explanation: str
    source_seconds: int | None


@dataclass(frozen=True, slots=True)
class QuizResult:
    score: int
    total: int
    results: list[QuestionResult]


@dataclass(frozen=True, slots=True)
class QuestionStats:
    question: str
    options: list[str]
    correct_option: int
    # First attempts that chose each option; skipped questions count in none of them.
    option_counts: list[int]
    answered: int


@dataclass(frozen=True, slots=True)
class QuizStats:
    attempts: int
    total: int
    average_score: float | None
    # Index = number of correct answers.
    score_distribution: list[int]
    questions: list[QuestionStats]


def public_questions(quiz: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [{"question": q["question"], "options": list(q["options"])} for q in quiz]


def grade(quiz: Sequence[Mapping[str, Any]] | None, answers: Sequence[int | None]) -> QuizResult:
    if not quiz:
        raise Conflict("This session has no quiz yet.", code="quiz_unavailable")
    if len(answers) != len(quiz):
        raise ValidationFailed(f"Expected {len(quiz)} answers, got {len(answers)}.")
    results = []
    for question, selected in zip(quiz, answers, strict=True):
        if selected is not None and not 0 <= selected < len(question["options"]):
            raise ValidationFailed("An answer refers to an option that does not exist.")
        correct = int(question["correct_option"])
        results.append(
            QuestionResult(
                selected=selected,
                correct_option=correct,
                is_correct=selected == correct,
                explanation=question.get("explanation", ""),
                source_seconds=question.get("source_seconds"),
            )
        )
    return QuizResult(score=sum(r.is_correct for r in results), total=len(results), results=results)


async def has_attempted(db: AsyncSession, session_id: uuid.UUID, participant: str) -> bool:
    found = await db.scalar(
        select(QuizAttempt.id).where(
            QuizAttempt.session_id == session_id, QuizAttempt.participant_key == participant
        )
    )
    return found is not None


async def record_first_attempt(
    db: AsyncSession,
    session: TrainingSession,
    participant: str,
    answers: Sequence[int | None],
    result: QuizResult,
) -> bool:
    """Stores a listener's attempt if it is their first; returns whether it was stored."""
    if await has_attempted(db, session.id, participant):
        return False
    stored = await db.scalar(
        select(func.count()).select_from(QuizAttempt).where(QuizAttempt.session_id == session.id)
    )
    if (stored or 0) >= MAX_RECORDED_ATTEMPTS:
        return False
    db.add(
        QuizAttempt(
            session_id=session.id,
            participant_key=participant,
            answers=list(answers),
            score=result.score,
            total=result.total,
        )
    )
    try:
        await db.commit()
    except IntegrityError:  # a concurrent first attempt of the same listener won
        await db.rollback()
        return False
    return True


async def discard_attempts(db: AsyncSession, session: TrainingSession) -> None:
    """Drops statistics that no longer match the quiz (caller commits)."""
    await db.execute(delete(QuizAttempt).where(QuizAttempt.session_id == session.id))


async def statistics(db: AsyncSession, session: TrainingSession) -> QuizStats:
    quiz = session.quiz
    if not quiz:
        raise Conflict("This session has no quiz yet.", code="quiz_unavailable")
    rows = (
        await db.execute(select(QuizAttempt.answers).where(QuizAttempt.session_id == session.id))
    ).scalars()
    attempts = [answers for answers in rows if len(answers) == len(quiz)]

    distribution = [0] * (len(quiz) + 1)
    questions = []
    for index, question in enumerate(quiz):
        counts = [0] * len(question["options"])
        for answers in attempts:
            choice = answers[index]
            if isinstance(choice, int) and 0 <= choice < len(counts):
                counts[choice] += 1
        questions.append(
            QuestionStats(
                question=question["question"],
                options=list(question["options"]),
                correct_option=int(question["correct_option"]),
                option_counts=counts,
                answered=sum(counts),
            )
        )
    for answers in attempts:
        score = sum(
            answer == int(question["correct_option"])
            for answer, question in zip(answers, quiz, strict=True)
        )
        distribution[score] += 1
    average = (
        round(sum(score * n for score, n in enumerate(distribution)) / len(attempts), 2)
        if attempts
        else None
    )
    return QuizStats(
        attempts=len(attempts),
        total=len(quiz),
        average_score=average,
        score_distribution=distribution,
        questions=questions,
    )
