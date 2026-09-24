import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, Timestamps, UUIDPrimaryKey, utcnow
from sonora.models._enum import enum_column

if TYPE_CHECKING:
    from sonora.models.training_session import TrainingSession


class JobType(StrEnum):
    PROCESS_SESSION = "process_session"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Job(UUIDPrimaryKey, Timestamps, Base):
    """Database-backed work queue entry.

    Workers claim jobs with an optimistic ``UPDATE ... WHERE status = ...`` and hold a
    lease (``locked_until``) that they extend while working; a crashed worker's job is
    picked up again once the lease expires. Works the same on SQLite and PostgreSQL.
    """

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_after", "status", "run_after"),)

    type: Mapped[JobType] = mapped_column(enum_column(JobType, 32))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    session: Mapped["TrainingSession | None"] = relationship(lazy="raise")
    status: Mapped[JobStatus] = mapped_column(enum_column(JobStatus, 16))
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int]
    run_after: Mapped[datetime] = mapped_column(default=utcnow)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    locked_until: Mapped[datetime | None]
    # Internal diagnostics only; never shown to users.
    last_error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
