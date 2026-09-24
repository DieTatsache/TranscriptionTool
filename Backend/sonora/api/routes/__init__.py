from fastapi import APIRouter

from sonora.api.routes import account, auth, chat, meta, public, sessions, shares

api_router = APIRouter()
for module in (meta, auth, account, sessions, chat, shares, public):
    api_router.include_router(module.router)
