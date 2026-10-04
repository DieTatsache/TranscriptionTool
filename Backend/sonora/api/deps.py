"""FastAPI dependencies: services, database session, authentication, listener identity
and rate limits."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.config import Settings
from sonora.container import Services
from sonora.errors import NotAuthenticated, PermissionDenied
from sonora.models import TrainingSession, User
from sonora.security import is_token, new_token, token_digest, tokens_match
from sonora.services import auth as auth_service
from sonora.services import sessions as sessions_service
from sonora.services.auth import AuthContext, ClientInfo

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"
# A year: long enough to cover share links, below browsers' 400-day cookie cap.
PARTICIPANT_COOKIE_MAX_AGE = 365 * 24 * 3600


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]


async def get_db(services: ServicesDep) -> AsyncIterator[AsyncSession]:
    async with services.sessionmaker() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]


def client_ip(request: Request) -> str:
    # Behind the reverse proxy this is the real client (uvicorn --proxy-headers).
    return request.client.host if request.client else "unknown"


def client_info(request: Request) -> ClientInfo:
    return ClientInfo(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


async def get_auth(request: Request, db: DB, services: ServicesDep) -> AuthContext:
    token = request.cookies.get(services.settings.session_cookie_name)
    if not token:
        raise NotAuthenticated()
    auth = await auth_service.resolve_session(db, services, token)
    if auth is None:
        raise NotAuthenticated(
            "Your session has expired. Please sign in again.",
            code="session_expired",
            clear_cookie=True,
        )
    if request.method not in SAFE_METHODS:
        provided = request.headers.get(CSRF_HEADER, "")
        if not provided or not tokens_match(auth.session.csrf_token, provided):
            raise PermissionDenied("Missing or invalid CSRF token.", code="csrf_failed")
    return auth


Auth = Annotated[AuthContext, Depends(get_auth)]


async def get_current_user(auth: Auth) -> User:
    return auth.user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_viewer(request: Request, db: DB, services: ServicesDep) -> User | None:
    """The signed-in user on public pages, if any; never fails (no CSRF: read-only use)."""
    token = request.cookies.get(services.settings.session_cookie_name)
    if not token:
        return None
    auth = await auth_service.resolve_session(db, services, token)
    return auth.user if auth else None


Viewer = Annotated[User | None, Depends(get_viewer)]


def read_participant(request: Request, settings: Settings) -> str | None:
    """The anonymous listener id from the participant cookie (well-formed values only)."""
    token = request.cookies.get(settings.participant_cookie_name, "")
    return token if is_token(token) else None


def issue_participant(response: Response, settings: Settings) -> str:
    token = new_token()
    response.set_cookie(
        settings.participant_cookie_name,
        token,
        max_age=PARTICIPANT_COOKIE_MAX_AGE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",  # a cross-site page can't submit on a listener's behalf
    )
    return token


def rate_limit_participant(rule: str, scope: str) -> Any:
    """Per-listener limit on public endpoints (keyed by a hash of the participant cookie)."""

    async def dependency(request: Request, services: ServicesDep) -> None:
        participant = read_participant(request, services.settings)
        if participant is not None:
            await services.rate_limiter.hit(rule, scope, token_digest(participant))

    return Depends(dependency)


async def get_owned_session(session_id: uuid.UUID, db: DB, user: CurrentUser) -> TrainingSession:
    return await sessions_service.get_owned(db, user, session_id)


async def get_owned_session_with_content(
    session_id: uuid.UUID, db: DB, user: CurrentUser
) -> TrainingSession:
    return await sessions_service.get_owned(db, user, session_id, with_content=True)


OwnedSession = Annotated[TrainingSession, Depends(get_owned_session)]
OwnedSessionWithContent = Annotated[TrainingSession, Depends(get_owned_session_with_content)]


def rate_limit_ip(rule: str, scope: str) -> Any:
    """Per-client-IP limit, for endpoints that don't require a signed-in user."""

    async def dependency(request: Request, services: ServicesDep) -> None:
        await services.rate_limiter.hit(rule, scope, client_ip(request))

    return Depends(dependency)
