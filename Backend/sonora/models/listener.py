"""Anonymous listener input on shared sessions: first quiz attempts and feedback."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, UUIDPrimaryKey, utcnow
from sonora.db.types import JSONType

if TYPE_CHECKING:
    from sonora.models.training_session import TrainingSession


class QuizAttempt(UUIDPrimaryKey, Base):
    """A listener's first graded attempt at a shared quiz; later attempts aren't stored.

    ``participant_key`` is the SHA-256 of the session id and the listener's random cookie,
    so attempts of one browser can't be linked across sessions.
    """

    __tablename__ = "quiz_attempts"
    __table_args__ = (UniqueConstraint("session_id", "participant_key"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE")
    )
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    session: Mapped["TrainingSession"] = relationship(lazy="raise")
    participant_key: Mapped[str] = mapped_column(String(64))
    # Selected option per question (None = skipped), in quiz order.
    answers: Mapped[list[int | None]] = mapped_column(JSONType)
    score: Mapped[int]
    total: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class FeedbackResponse(UUIDPrimaryKey, Base):
    """One listener's anonymous feedback on a session (one per participant, see QuizAttempt)."""

    __tablename__ = "feedback_responses"
    __table_args__ = (
        UniqueConstraint("session_id", "participant_key"),
        Index("ix_feedback_responses_session_created", "session_id", "created_at"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE")
    )
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    session: Mapped["TrainingSession"] = relationship(lazy="raise")
    participant_key: Mapped[str] = mapped_column(String(64))
    form_version: Mapped[int]
    # Question id -> selected option index (see sonora.feedback).
    ratings: Mapped[dict[str, Any]] = mapped_column(JSONType)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
