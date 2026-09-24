"""Quiz presentation and server-side grading.

Correct answers never leave the server before an attempt is submitted, so participants
can't read them from the network tab.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sonora.errors import Conflict, ValidationFailed


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
