from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from sonora.db.base import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    # Stored normalised (trimmed, lower-case) so uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    bio: Mapped[str] = mapped_column(String(1000), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(20))
    notify_on_ready: Mapped[bool] = mapped_column(default=True)
    password_changed_at: Mapped[datetime | None]
    # Reserved for email verification; not enforced yet.
    email_verified_at: Mapped[datetime | None]
