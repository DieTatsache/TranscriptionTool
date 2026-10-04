from fastapi import APIRouter, Request, Response

from sonora.api.deps import DB, Auth, ServicesDep, client_info, rate_limit_ip
from sonora.api.schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut
from sonora.config import Settings
from sonora.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,  # not readable by scripts: an XSS can't steal the session
        samesite="strict",  # never sent on cross-site requests
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


async def _end_previous_session(request: Request, db: DB, settings: Settings) -> None:
    # A successful sign-in replaces the browser's previous session instead of leaving it valid.
    previous = request.cookies.get(settings.session_cookie_name)
    if previous:
        await auth_service.revoke_token(db, previous)


@router.post(
    "/register",
    status_code=201,
    response_model=AuthResponse,
    dependencies=[rate_limit_ip("5/hour", "register")],
)
async def register(
    body: RegisterRequest, request: Request, response: Response, db: DB, services: ServicesDep
) -> AuthResponse:
    new = await auth_service.register(
        db,
        services,
        name=body.name,
        email=body.email,
        password=body.password,
        client=client_info(request),
    )
    await _end_previous_session(request, db, services.settings)
    set_session_cookie(response, new.token, services.settings)
    return AuthResponse(user=UserOut.model_validate(new.user), csrf_token=new.session.csrf_token)


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, db: DB, services: ServicesDep
) -> AuthResponse:
    new = await auth_service.login(
        db, services, email=body.email, password=body.password, client=client_info(request)
    )
    await _end_previous_session(request, db, services.settings)
    set_session_cookie(response, new.token, services.settings)
    return AuthResponse(user=UserOut.model_validate(new.user), csrf_token=new.session.csrf_token)


@router.post("/logout", status_code=204)
async def logout(auth: Auth, db: DB, services: ServicesDep) -> Response:
    await auth_service.logout(db, auth.session)
    response = Response(status_code=204)
    clear_session_cookie(response, services.settings)
    return response


@router.get("/me", response_model=AuthResponse)
async def me(auth: Auth) -> AuthResponse:
    """The signed-in user plus the CSRF token (used by the SPA after a page reload)."""
    return AuthResponse(user=UserOut.model_validate(auth.user), csrf_token=auth.session.csrf_token)
