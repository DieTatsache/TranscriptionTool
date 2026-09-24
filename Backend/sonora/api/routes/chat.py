from fastapi import APIRouter

from sonora.api.deps import DB, CurrentUser, OwnedSession, OwnedSessionWithContent, ServicesDep
from sonora.api.schemas import ChatAsk, ChatMessageOut
from sonora.services import chat as chat_service

router = APIRouter(prefix="/sessions/{session_id}/chat", tags=["chat"])


@router.get("", response_model=list[ChatMessageOut])
async def chat_history(session: OwnedSession, db: DB) -> list[ChatMessageOut]:
    return [ChatMessageOut.model_validate(m) for m in await chat_service.history(db, session)]


@router.post("", response_model=ChatMessageOut)
async def ask(
    body: ChatAsk,
    session: OwnedSessionWithContent,
    user: CurrentUser,
    db: DB,
    services: ServicesDep,
) -> ChatMessageOut:
    reply = await chat_service.ask(db, services, user, session, body.message)
    return ChatMessageOut.model_validate(reply)
