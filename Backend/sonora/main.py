"""Application factory: ``uvicorn sonora.main:create_app --factory``."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sonora import __version__
from sonora.api.middleware import BodySizeLimitMiddleware, OriginCheckMiddleware, SecurityMiddleware
from sonora.api.routes import api_router
from sonora.config import Settings, get_settings
from sonora.container import Services, build_services
from sonora.errors import install_error_handlers
from sonora.logs import configure_logging
from sonora.worker.runner import Worker

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"
WORKER_SHUTDOWN_GRACE_SECONDS = 5


def create_app(settings: Settings | None = None, *, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    if services is None:
        configure_logging(settings.log_level, json_output=settings.log_json)
        services = build_services(settings)
    app_services = services

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        worker_task = None
        if settings.worker_embedded:
            worker_task = asyncio.create_task(Worker(app_services).run(stop), name="worker")
        try:
            yield
        finally:
            stop.set()
            if worker_task is not None:
                # An interrupted job keeps its lease and is picked up again after restart.
                _done, pending = await asyncio.wait(
                    {worker_task}, timeout=WORKER_SHUTDOWN_GRACE_SECONDS
                )
                if pending:
                    worker_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await worker_task
            await app_services.aclose()

    docs = settings.docs_available
    app = FastAPI(
        title="Sonora API",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        swagger_ui_oauth2_redirect_url=None,
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
    )
    app.state.services = app_services
    install_error_handlers(app)
    app.include_router(api_router, prefix=API_PREFIX)

    # Added innermost first: the last one added wraps all the others.
    app.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=settings.max_json_body_bytes,
        route_limits={("POST", f"{API_PREFIX}/sessions"): settings.max_upload_bytes},
    )
    app.add_middleware(OriginCheckMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        SecurityMiddleware,
        hsts=settings.hsts_enabled,
        csp_exempt_prefixes=[f"{API_PREFIX}/docs"] if docs else [],
    )
    logger.info("Sonora API %s starting (%s)", __version__, settings.environment.value)
    return app
