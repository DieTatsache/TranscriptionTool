from typing import Annotated

from fastapi import APIRouter, Query, Response

from sonora.api.deps import DB, Auth, CurrentUser, ServicesDep
from sonora.api.routes.auth import clear_session_cookie
from sonora.api.schemas import (
    AccountDelete,
    ActivityOut,
    PasswordChange,
    PlanOut,
    ProfileUpdate,
    StatsOut,
    UsageOut,
    UserOut,
)
from sonora.plans import get_plan
from sonora.services import account as account_service
from sonora.services import activity

router = APIRouter(prefix="/me", tags=["account"])


@router.patch("", response_model=UserOut)
async def update_profile(body: ProfileUpdate, auth: Auth, db: DB, services: ServicesDep) -> UserOut:
    user = await account_service.update_profile(
        db,
        services,
        auth,
        account_service.ProfileChanges(
            name=body.name,
            bio=body.bio,
            notify_on_ready=body.notify_on_ready,
            email=body.email,
            current_password=body.current_password,
        ),
    )
    return UserOut.model_validate(user)


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordChange, auth: Auth, db: DB, services: ServicesDep
) -> Response:
    await account_service.change_password(
        db, services, auth, current=body.current_password, new=body.new_password
    )
    return Response(status_code=204)


@router.post("/delete", status_code=204)
async def delete_account(
    body: AccountDelete, auth: Auth, db: DB, services: ServicesDep
) -> Response:
    await account_service.delete_account(db, services, auth, body.password)
    response = Response(status_code=204)
    clear_session_cookie(response, services.settings)
    return response


@router.get("/usage", response_model=UsageOut)
async def usage(user: CurrentUser, db: DB) -> UsageOut:
    return UsageOut(
        plan=PlanOut.model_validate(get_plan(user.plan)),
        sessions_this_month=await activity.sessions_this_month(db, user.id),
        remaining_this_month=await activity.remaining_sessions(db, user),
    )


@router.get("/stats", response_model=StatsOut)
async def stats(user: CurrentUser, db: DB) -> StatsOut:
    return StatsOut.model_validate(await account_service.stats(db, user))


@router.get("/activity", response_model=list[ActivityOut])
async def recent_activity(
    user: CurrentUser, db: DB, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[ActivityOut]:
    return [ActivityOut.model_validate(e) for e in await activity.recent(db, user.id, limit)]
