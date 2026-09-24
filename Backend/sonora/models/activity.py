import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, UUIDPrimaryKey, utcnow
from sonora.models._enum import enum_column

if TYPE_CHECKING:
    from sonora.models.user import User


class ActivityType(StrEnum):
    ACCOUNT_CREATED = "account_created"
    SESSION_CREATED = "session_created"
    SESSION_DELETED = "session_deleted"
    SHARE_CREATED = "share_created"
    SHARE_REVOKED = "share_revoked"
    PROFILE_UPDATED = "profile_updated"
    EMAIL_CHANGED = "email_changed"
    PASSWORD_CHANGED = "password_changed"  # noqa: S105


class ActivityEvent(UUIDPrimaryKey, Base):
    """Append-only per-user activity log (profile page feed and usage accounting).

    Monthly quotas count ``session_created`` events, so deleting a session does not give
    back quota that was already spent on processing.
    """

    __tablename__ = "activity_events"
    __table_args__ = (Index("ix_activity_events_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    user: Mapped["User"] = relationship(lazy="raise")
    type: Mapped[ActivityType] = mapped_column(enum_column(ActivityType, 32))
    detail: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
