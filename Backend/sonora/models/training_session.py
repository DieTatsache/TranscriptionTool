import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, Timestamps, UUIDPrimaryKey
from sonora.db.types import JSONType
from sonora.models._enum import enum_column

if TYPE_CHECKING:
    from sonora.models.user import User


class SessionStatus(StrEnum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class TrainingSession(UUIDPrimaryKey, Timestamps, Base):
    """A recorded lecture/training session and everything generated from it.

    Generated content is stored as JSON documents (always read and written as a whole)
    and deferred with raiseload, so list queries never pull transcripts by accident.
    """

    __tablename__ = "training_sessions"
    __table_args__ = (Index("ix_training_sessions_owner_created", "owner_id", "created_at"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    owner: Mapped["User"] = relationship(lazy="raise")
    title: Mapped[str] = mapped_column(String(200))
    # False once the owner chose a title; generation then keeps it.
    auto_title: Mapped[bool] = mapped_column(default=True)
    status: Mapped[SessionStatus] = mapped_column(enum_column(SessionStatus))
    # User-facing reason for status=failed (never raw exception text).
    error_message: Mapped[str | None] = mapped_column(String(300))
    language: Mapped[str | None] = mapped_column(String(16))
    duration_seconds: Mapped[int | None]
    quiz_count: Mapped[int] = mapped_column(default=0)
    ready_at: Mapped[datetime | None]

    # Uploaded audio; cleared once transcribed unless SONORA_KEEP_AUDIO is set.
    audio_key: Mapped[str | None] = mapped_column(String(64))
    audio_mime: Mapped[str | None] = mapped_column(String(50))
    audio_size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    transcript: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONType, deferred=True, deferred_raiseload=True
    )
    script: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType, deferred=True, deferred_raiseload=True
    )
    quiz: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONType, deferred=True, deferred_raiseload=True
    )
