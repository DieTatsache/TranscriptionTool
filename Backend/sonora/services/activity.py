"""Per-user activity log and the usage numbers derived from it."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.db import utcnow
from sonora.models import ActivityEvent, ActivityType, User
from sonora.plans import get_plan


def record(db: AsyncSession, user_id: uuid.UUID, type_: ActivityType, detail: str = "") -> None:
    """Adds an event to the caller's transaction (committed together with the change)."""
    db.add(ActivityEvent(user_id=user_id, type=type_, detail=detail[:300]))


async def recent(db: AsyncSession, user_id: uuid.UUID, limit: int) -> list[ActivityEvent]:
    rows = await db.scalars(
        select(ActivityEvent)
        .where(ActivityEvent.user_id == user_id)
        .order_by(ActivityEvent.created_at.desc())
        .limit(limit)
    )
    return list(rows)


def month_start(now: datetime | None = None) -> datetime:
    now = (now or utcnow()).astimezone(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def sessions_this_month(db: AsyncSession, user_id: uuid.UUID) -> int:
    count = await db.scalar(
        select(func.count())
        .select_from(ActivityEvent)
        .where(
            ActivityEvent.user_id == user_id,
            ActivityEvent.type == ActivityType.SESSION_CREATED,
            ActivityEvent.created_at >= month_start(),
        )
    )
    return count or 0


async def remaining_sessions(db: AsyncSession, user: User) -> int | None:
    """Sessions left this month, or None for plans without a cap."""
    limit = get_plan(user.plan).monthly_session_limit
    if limit is None:
        return None
    return max(0, limit - await sessions_this_month(db, user.id))
