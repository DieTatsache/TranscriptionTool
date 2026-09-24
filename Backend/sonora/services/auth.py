"""Registration, sign-in and server-side sessions.

A session is an opaque 256-bit token in an HttpOnly cookie; the database only stores its
SHA-256. Each session also has a CSRF token that the SPA must echo in ``X-CSRF-Token``
on state-changing requests. Sessions expire absolutely and after inactivity.
"""

import logging
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.container import Services
from sonora.db import rowcount, utcnow
from sonora.errors import (
    Conflict,
    NotAuthenticated,
    PermissionDenied,
    RateLimited,
    ValidationFailed,
)
from sonora.models import ActivityType, AuthSession, User
from sonora.security import new_token, password_problem, token_digest
from sonora.services import activity

logger = logging.getLogger(__name__)

# Touching last_seen_at on every request would turn reads into writes.
LAST_SEEN_RESOLUTION = timedelta(minutes=5)
LOGIN_ATTEMPTS_PER_IP = "20/minute"


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    session: AuthSession


@dataclass(frozen=True, slots=True)
class NewSession:
    user: User
    session: AuthSession
    token: str  # goes into the cookie; never stored


@dataclass(frozen=True, slots=True)
class ClientInfo:
    ip: str | None
    user_agent: str | None


def normalize_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()


def _login_failure_rule(services: Services) -> str:
    s = services.settings
    return f"{s.login_max_failures}/{s.login_lockout_minutes} minutes"


def _new_session(user: User, services: Services, client: ClientInfo) -> tuple[AuthSession, str]:
    now = utcnow()
    token = new_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=token_digest(token),
        csrf_token=new_token(),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=services.settings.session_ttl_hours),
        ip_address=(client.ip or "")[:45] or None,
        user_agent=(client.user_agent or "")[:255] or None,
    )
    return session, token


async def email_in_use(db: AsyncSession, email: str) -> bool:
    """Friendly pre-check; the unique constraint remains the source of truth under races."""
    return await db.scalar(select(User.id).where(User.email == email)) is not None


def ensure_acceptable_password(services: Services, password: str, email: str) -> None:
    problem = password_problem(
        password, min_length=services.settings.password_min_length, email=email
    )
    if problem:
        raise ValidationFailed(
            problem, code="weak_password", details=[{"field": "password", "message": problem}]
        )


async def register(
    db: AsyncSession,
    services: Services,
    *,
    name: str,
    email: str,
    password: str,
    client: ClientInfo,
) -> NewSession:
    if not services.settings.registration_enabled:
        raise PermissionDenied("Registration is currently closed.", code="registration_disabled")
    email = normalize_email(email)
    ensure_acceptable_password(services, password, email)
    if await email_in_use(db, email):
        # Registration inherently reveals whether an email is known; it is rate limited per IP.
        raise Conflict("An account with this email already exists.", code="email_taken")

    user = User(
        id=uuid.uuid4(),
        name=name,
        email=email,
        password_hash=await services.passwords.hash(password),
        plan=services.settings.default_plan,
    )
    db.add(user)
    activity.record(db, user.id, ActivityType.ACCOUNT_CREATED)
    session, token = _new_session(user, services, client)
    db.add(session)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise Conflict("An account with this email already exists.", code="email_taken") from None
    logger.info("account created user=%s", user.id)
    return NewSession(user, session, token)


async def login(
    db: AsyncSession, services: Services, *, email: str, password: str, client: ClientInfo
) -> NewSession:
    limiter = services.rate_limiter
    await limiter.hit(LOGIN_ATTEMPTS_PER_IP, "login-ip", client.ip or "unknown")

    email = normalize_email(email)
    # Failures are counted per email whether or not the account exists (no enumeration).
    email_key = token_digest(email)
    rule = _login_failure_rule(services)
    if not await limiter.allows(rule, "login-failures", email_key):
        retry_after = await limiter.retry_after(rule, "login-failures", email_key)
        raise RateLimited(
            "Too many failed sign-in attempts. Please try again later.",
            code="login_locked",
            headers={"Retry-After": str(retry_after)},
        )

    user = await db.scalar(select(User).where(User.email == email))
    # Runs the hash check even for unknown emails so timing doesn't reveal accounts.
    valid = await services.passwords.verify(user.password_hash if user else None, password)
    if user is None or not valid:
        await limiter.hit(rule, "login-failures", email_key)
        logger.info("failed sign-in attempt ip=%s", client.ip)
        raise NotAuthenticated("Invalid email or password.", code="invalid_credentials")

    await limiter.reset(rule, "login-failures", email_key)
    if services.passwords.needs_rehash(user.password_hash):
        user.password_hash = await services.passwords.hash(password)
    session, token = _new_session(user, services, client)
    db.add(session)
    await db.commit()
    logger.info("signed in user=%s", user.id)
    return NewSession(user, session, token)


async def resolve_session(db: AsyncSession, services: Services, token: str) -> AuthContext | None:
    row = (
        await db.execute(
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(AuthSession.token_hash == token_digest(token))
        )
    ).first()
    if row is None:
        return None
    session, user = row
    now = utcnow()
    idle_limit = timedelta(hours=services.settings.session_idle_hours)
    if session.expires_at <= now or session.last_seen_at + idle_limit <= now:
        await db.delete(session)
        await db.commit()
        return None
    if now - session.last_seen_at >= LAST_SEEN_RESOLUTION:
        session.last_seen_at = now
        await db.commit()
    return AuthContext(user, session)


async def logout(db: AsyncSession, session: AuthSession) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.id == session.id))
    await db.commit()


async def revoke_token(db: AsyncSession, token: str) -> None:
    """Ends the session behind a cookie value, if any (used before signing in again)."""
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == token_digest(token)))
    await db.commit()


async def revoke_other_sessions(db: AsyncSession, user_id: uuid.UUID, keep: uuid.UUID) -> None:
    """Signs out every other browser (after password or email changes). Caller commits."""
    await db.execute(
        delete(AuthSession).where(AuthSession.user_id == user_id, AuthSession.id != keep)
    )


async def purge_expired(db: AsyncSession, services: Services) -> int:
    now = utcnow()
    idle_cutoff = now - timedelta(hours=services.settings.session_idle_hours)
    result = await db.execute(
        delete(AuthSession).where(
            (AuthSession.expires_at <= now) | (AuthSession.last_seen_at <= idle_cutoff)
        )
    )
    await db.commit()
    return rowcount(result)
