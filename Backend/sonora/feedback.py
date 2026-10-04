"""The listener feedback form.

One fixed form for every session, defined here so that the participant page, server-side
validation and the lecturer's results all use the same questions. Closed questions are
answered with an option index; the single open question is the free-text comment.
Responses store the form version, so a future form never mixes with older answers.
"""

from dataclasses import dataclass
from typing import Literal

QuestionType = Literal["stars", "scale", "choice", "text"]

FORM_VERSION = 1
COMMENT_QUESTION = "comment"
COMMENT_MAX_LENGTH = 800


@dataclass(frozen=True, slots=True)
class FeedbackQuestion:
    id: str
    type: QuestionType
    label: str
    # Closed questions: the label of each answer, by option index.
    options: tuple[str, ...] = ()
    # End labels of a scale.
    low: str | None = None
    high: str | None = None
    placeholder: str | None = None
    max_length: int | None = None
    required: bool = True

    @property
    def numeric(self) -> bool:
        """Ratings whose average is meaningful (option i means the value i + 1)."""
        return self.type in ("stars", "scale")


_SEVEN_POINTS = tuple(str(value) for value in range(1, 8))

FEEDBACK_FORM: tuple[FeedbackQuestion, ...] = (
    FeedbackQuestion(
        "overall",
        "stars",
        "Overall session quality",
        options=("Poor", "Fair", "Good", "Very good", "Excellent"),
    ),
    FeedbackQuestion(
        "clarity",
        "scale",
        "How clearly was the content explained?",
        options=_SEVEN_POINTS,
        low="Very unclear",
        high="Crystal clear",
    ),
    FeedbackQuestion(
        "pace",
        "choice",
        "How was the pace of the session?",
        options=("Too slow", "Just right", "Too fast"),
    ),
    FeedbackQuestion(
        "relevance",
        "scale",
        "How relevant was the content to you?",
        options=_SEVEN_POINTS,
        low="Not relevant",
        high="Extremely relevant",
    ),
    FeedbackQuestion(
        COMMENT_QUESTION,
        "text",
        "Anything you'd like the trainer to know?",
        placeholder="Optional — your comment stays anonymous.",
        max_length=COMMENT_MAX_LENGTH,
        required=False,
    ),
)

RATING_QUESTIONS: tuple[FeedbackQuestion, ...] = tuple(
    question for question in FEEDBACK_FORM if question.type != "text"
)
