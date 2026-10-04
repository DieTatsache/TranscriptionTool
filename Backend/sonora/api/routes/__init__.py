from fastapi import APIRouter

from sonora.api.routes import (
    account,
    analysis,
    auth,
    billing,
    chat,
    feedback,
    meta,
    public,
    sessions,
    shares,
)

api_router = APIRouter()
for module in (meta, auth, account, billing, sessions, chat, analysis, feedback, shares, public):
    api_router.include_router(module.router)
