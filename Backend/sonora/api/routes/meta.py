from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sonora import __version__
from sonora.ai.text import LANGUAGE_NAMES
from sonora.api.deps import DB, ServicesDep
from sonora.api.schemas import LanguageOut, MetaOut
from sonora.models import ShareTab

router = APIRouter(tags=["meta"])


@router.get("/health", include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", include_in_schema=False)
async def readiness(db: DB) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})


@router.get("/meta", response_model=MetaOut)
async def meta(services: ServicesDep) -> MetaOut:
    """Public client configuration (limits and feature switches)."""
    settings = services.settings
    return MetaOut(
        version=__version__,
        registration_enabled=settings.registration_enabled,
        password_min_length=settings.password_min_length,
        max_upload_mb=settings.max_upload_mb,
        max_audio_minutes=settings.max_audio_minutes,
        languages=[LanguageOut(code=c, name=n) for c, n in sorted(LANGUAGE_NAMES.items())],
        share_tabs=list(ShareTab),
    )
