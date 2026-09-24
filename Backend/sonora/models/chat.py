import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, UUIDPrimaryKey, utcnow
from sonora.models._enum import enum_column

if TYPE_CHECKING:
    from sonora.models.training_session import TrainingSession


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSource(StrEnum):
    LESSON = "lesson"  # answered from the transcript
    KNOWLEDGE = "knowledge"  # not covered by the lecture; general knowledge


class ChatMessage(UUIDPrimaryKey, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_created", "session_id", "created_at"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("training_sessions.id", ondelete="CASCADE")
    )
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    session: Mapped["TrainingSession"] = relationship(lazy="raise")
    role: Mapped[ChatRole] = mapped_column(enum_column(ChatRole, 16))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[ChatSource | None] = mapped_column(enum_column(ChatSource, 16))
    cite_seconds: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
