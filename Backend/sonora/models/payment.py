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


class PaymentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(UUIDPrimaryKey, Base):
    """One charge for a plan (the payment history).

    Card data never reaches the server: the browser hands the payment provider's token to
    the API, and only what the provider reports back (brand, last four digits) is stored.
    """

    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Declared for flush ordering (parent rows insert first); never lazy-loaded.
    user: Mapped["User"] = relationship(lazy="raise")
    plan: Mapped[str] = mapped_column(String(20))
    amount_cents: Mapped[int]
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[PaymentStatus] = mapped_column(enum_column(PaymentStatus, 16))
    provider: Mapped[str] = mapped_column(String(20))
    # The provider's charge id.
    reference: Mapped[str] = mapped_column(String(64))
    card_brand: Mapped[str | None] = mapped_column(String(20))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    failure_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
