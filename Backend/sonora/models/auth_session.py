import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sonora.db.base import Base, UUIDPrimaryKey, utcnow

if TYPE_CHECKING:
    from sonora.models.user import User


class AuthSession(UUIDPrimaryKey, Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored,
    so a database leak cannot be replayed as a login."""

    __tablename__ = "auth_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    user: Mapped["User"] = relationship(lazy="raise")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
