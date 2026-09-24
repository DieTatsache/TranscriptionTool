import uuid

from fastapi import APIRouter, Response

from sonora.api.deps import DB, CurrentUser, OwnedSession
from sonora.api.schemas import ShareCreate, ShareOut
from sonora.services import shares as shares_service

router = APIRouter(prefix="/sessions/{session_id}/shares", tags=["sharing"])


@router.get("", response_model=list[ShareOut])
async def list_shares(session: OwnedSession, db: DB) -> list[ShareOut]:
    return [ShareOut.model_validate(s) for s in await shares_service.list_active(db, session)]


@router.post("", status_code=201, response_model=ShareOut)
async def create_share(
    body: ShareCreate, session: OwnedSession, user: CurrentUser, db: DB
) -> ShareOut:
    link = await shares_service.create(
        db, user, session, tabs=body.tabs, expires_in_days=body.expires_in_days
    )
    return ShareOut.model_validate(link)


@router.delete("/{share_id}", status_code=204)
async def revoke_share(
    share_id: uuid.UUID, session: OwnedSession, user: CurrentUser, db: DB
) -> Response:
    await shares_service.revoke(db, user, session, share_id)
    return Response(status_code=204)
