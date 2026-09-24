import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, UUIDPrimaryKey, utcnow
from sonora.db.types import JSONType

if TYPE_CHECKING:
    from sonora.models.training_session import TrainingSession


class ShareTab(StrEnum):
    SCRIPT = "script"
    QUIZ = "quiz"
    TRANSCRIPT = "transcript"


class ShareLink(UUIDPrimaryKey, Base):
    """Read-only public access to selected parts of one session.

    The token is stored in plain text on purpose: it only unlocks content that lives in
    the same database, so hashing would not protect anything, while plain storage lets
    trainers copy an existing link again. Tokens are 256-bit random values.
    """

    __tablename__ = "share_links"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE"), index=True
    )
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    session: Mapped["TrainingSession"] = relationship(lazy="raise")
    token: Mapped[str] = mapped_column(String(64), unique=True)
    tabs: Mapped[list[str]] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime | None]
