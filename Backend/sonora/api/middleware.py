"""Pure ASGI middleware (no buffering, safe with streamed uploads)."""

import logging
import re
import uuid
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sonora.errors import RequestTooLarge, error_response
from sonora.logs import request_id_var

logger = logging.getLogger(__name__)

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

BASE_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cache-Control": "no-store",
}
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


class SecurityMiddleware:
    """Request ids, security headers on every response, and a JSON 500 for crashes."""

    def __init__(self, app: ASGIApp, *, hsts: bool, csp_exempt_prefixes: Iterable[str] = ()):
        self.app = app
        self.hsts = hsts
        self.csp_exempt_prefixes = tuple(csp_exempt_prefixes)  # interactive API docs

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else uuid.uuid4().hex
        context_token = request_id_var.set(request_id)
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for name, value in BASE_SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if not scope["path"].startswith(self.csp_exempt_prefixes):
                    headers.setdefault("Content-Security-Policy", API_CSP)
                if self.hsts:
                    headers.setdefault(
                        "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
                    )
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            logger.exception("unhandled error on %s %s", scope["method"], scope["path"])
            if started:
                raise
            response = error_response(500, "internal_error", "An unexpected error occurred.")
            await response(scope, receive, send_with_headers)
        finally:
            request_id_var.reset(context_token)


class OriginCheckMiddleware:
    """Rejects state-changing requests from foreign origins (CSRF defence in depth).

    Browsers always send ``Origin`` on cross-origin POST/PUT/PATCH/DELETE. Requests without
    it come from non-browser clients, which can't be CSRF vehicles.
    """

    def __init__(self, app: ASGIApp, *, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed = frozenset(origin.rstrip("/") for origin in allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in _UNSAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin is not None and not self._allowed(origin, headers.get("host", "")):
                response = error_response(
                    403, "origin_not_allowed", "Cross-origin requests are not allowed."
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _allowed(self, origin: str, host: str) -> bool:
        if origin.rstrip("/") in self.allowed:
            return True
        # Same-origin calls (e.g. the API docs). The Host header can't be forged by a
        # cross-site page, so this doesn't open a CSRF path.
        return bool(host) and urlsplit(origin).netloc == host


class BodySizeLimitMiddleware:
    """Caps request bodies: checks Content-Length up front and counts streamed bytes."""

    def __init__(
        self, app: ASGIApp, *, default_limit: int, route_limits: Mapping[tuple[str, str], int]
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.route_limits = dict(route_limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.route_limits.get(
            (scope["method"], scope["path"].rstrip("/")), self.default_limit
        )
        declared = Headers(scope=scope).get("content-length")
        if declared is not None:
            if not declared.isdigit():
                await error_response(400, "bad_request", "Invalid Content-Length.")(
                    scope, receive, send
                )
                return
            if int(declared) > limit:
                await error_response(413, "payload_too_large", "The request body is too large.")(
                    scope, receive, send
                )
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestTooLarge()
            return message

        await self.app(scope, limited_receive, send)
