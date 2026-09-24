"""Profile, credentials and account lifecycle for the signed-in user."""

import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.container import Services
from sonora.db import utcnow
from sonora.errors import Conflict, PermissionDenied, ValidationFailed
from sonora.models import ActivityType, TrainingSession, User
from sonora.services import activity
from sonora.services import auth as auth_service
from sonora.services.auth import (
    AuthContext,
    ensure_acceptable_password,
    normalize_email,
    revoke_other_sessions,
)

logger = logging.getLogger(__name__)

# Per user, for endpoints that verify the current password.
PASSWORD_CHECKS = "5/15 minutes"  # noqa: S105


@dataclass(frozen=True, slots=True)
class ProfileChanges:
    name: str | None = None
    bio: str | None = None
    notify_on_ready: bool | None = None
    email: str | None = None
    current_password: str | None = None


@dataclass(frozen=True, slots=True)
class Stats:
    total_sessions: int
    quiz_questions: int
    audio_seconds: int
    sessions_this_month: int


async def _confirm_password(services: Services, user: User, password: str | None) -> None:
    await services.rate_limiter.hit(
        PASSWORD_CHECKS,
        "password-check",
        str(user.id),
        message="Too many password attempts. Please try again later.",
    )
    if not password or not await services.passwords.verify(user.password_hash, password):
        raise PermissionDenied("The current password is incorrect.", code="invalid_password")


async def update_profile(
    db: AsyncSession, services: Services, auth: AuthContext, changes: ProfileChanges
) -> User:
    user = auth.user
    profile_changed = False
    if changes.name is not None and changes.name != user.name:
        user.name = changes.name
        profile_changed = True
    if changes.bio is not None and changes.bio != user.bio:
        user.bio = changes.bio
        profile_changed = True
    if changes.notify_on_ready is not None and changes.notify_on_ready != user.notify_on_ready:
        user.notify_on_ready = changes.notify_on_ready
        profile_changed = True

    if changes.email is not None and normalize_email(changes.email) != user.email:
        # The email is the login identifier: changing it needs the password and ends
        # every other session.
        await _confirm_password(services, user, changes.current_password)
        new_email = normalize_email(changes.email)
        if await auth_service.email_in_use(db, new_email):
            raise Conflict("An account with this email already exists.", code="email_taken")
        user.email = new_email
        user.email_verified_at = None
        try:
            # Flush now: a lost uniqueness race must surface here, not as an autoflush
            # inside a later statement.
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise Conflict(
                "An account with this email already exists.", code="email_taken"
            ) from None
        await revoke_other_sessions(db, user.id, keep=auth.session.id)
        activity.record(db, user.id, ActivityType.EMAIL_CHANGED)

    if profile_changed:
        activity.record(db, user.id, ActivityType.PROFILE_UPDATED)
    await db.commit()
    return user


async def change_password(
    db: AsyncSession, services: Services, auth: AuthContext, *, current: str, new: str
) -> None:
    user = auth.user
    await _confirm_password(services, user, current)
    if new == current:
        raise ValidationFailed(
            "The new password must differ from the current one.", code="weak_password"
        )
    ensure_acceptable_password(services, new, user.email)
    user.password_hash = await services.passwords.hash(new)
    user.password_changed_at = utcnow()
    await revoke_other_sessions(db, user.id, keep=auth.session.id)
    activity.record(db, user.id, ActivityType.PASSWORD_CHANGED)
    await db.commit()
    logger.info("password changed user=%s", user.id)


async def delete_account(
    db: AsyncSession, services: Services, auth: AuthContext, password: str
) -> None:
    """Erases the account and everything it owns (GDPR Art. 17)."""
    user = auth.user
    await _confirm_password(services, user, password)
    audio_keys = list(
        await db.scalars(
            select(TrainingSession.audio_key).where(
                TrainingSession.owner_id == user.id, TrainingSession.audio_key.is_not(None)
            )
        )
    )
    # Sessions, content, shares, chats, jobs, activity and sign-ins cascade in the database.
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    for key in audio_keys:
        services.storage.delete(key)
    logger.info("account deleted user=%s", user.id)


async def stats(db: AsyncSession, user: User) -> Stats:
    total, quiz_questions, audio_seconds = (
        await db.execute(
            select(
                func.count(TrainingSession.id),
                func.coalesce(func.sum(TrainingSession.quiz_count), 0),
                func.coalesce(func.sum(TrainingSession.duration_seconds), 0),
            ).where(TrainingSession.owner_id == user.id)
        )
    ).one()
    return Stats(
        total_sessions=int(total),
        quiz_questions=int(quiz_questions),
        audio_seconds=int(audio_seconds),
        sessions_this_month=await activity.sessions_this_month(db, user.id),
    )
