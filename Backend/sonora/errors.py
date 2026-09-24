"""Application errors and the JSON error envelope.

Every error response has the shape ``{"error": {"code": ..., "message": ..., "details"?: ...}}``
so clients can branch on stable codes instead of parsing messages. Internal details
(stack traces, SQL, submitted values) never reach the client.
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.code = code or type(self).code
        self.details = details
        self.headers = headers or {}
        super().__init__(self.message)


class BadRequest(AppError):
    pass


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Authentication required."

    def __init__(self, message: str | None = None, *, clear_cookie: bool = False, **kw: Any):
        super().__init__(message, **kw)
        self.clear_cookie = clear_cookie


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"
    message = "You are not allowed to do this."


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Not found."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state."


class UnsupportedMediaType(AppError):
    status_code = 415
    code = "unsupported_media_type"
    message = "Unsupported file type."


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"
    message = "Some fields are invalid."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Please try again later."


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "The service is temporarily unavailable. Please try again later."


class RequestTooLarge(StarletteHTTPException):
    """Raised while streaming a body; subclasses HTTPException so FastAPI re-raises it."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail="The request body is too large.")


_HTTP_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse({"error": error}, status_code=status_code, headers=headers)


def _validation_details(exc: RequestValidationError) -> list[dict[str, str]]:
    # Only location + message: pydantic's "input" would echo submitted secrets back.
    details = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
        details.append({"field": ".".join(loc) or "request", "message": str(err.get("msg", ""))})
    return details


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        response = error_response(
            exc.status_code, exc.code, exc.message, details=exc.details, headers=exc.headers
        )
        if isinstance(exc, NotAuthenticated) and exc.clear_cookie:
            settings = request.app.state.services.settings
            response.delete_cookie(
                settings.session_cookie_name,
                path="/",
                secure=settings.cookie_secure,
                httponly=True,
                samesite="strict",
            )
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422, "validation_error", "Some fields are invalid.", details=_validation_details(exc)
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return error_response(exc.status_code, code, message, headers=exc.headers)
