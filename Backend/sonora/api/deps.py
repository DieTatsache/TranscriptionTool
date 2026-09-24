"""FastAPI dependencies: services, database session, authentication and rate limits."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.container import Services
from sonora.errors import NotAuthenticated, PermissionDenied
from sonora.models import TrainingSession, User
from sonora.security import tokens_match
from sonora.services import auth as auth_service
from sonora.services import sessions as sessions_service
from sonora.services.auth import AuthContext, ClientInfo

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"


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
