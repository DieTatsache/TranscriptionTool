"""Plan purchase, cancellation and payment history of the signed-in user."""

from fastapi import APIRouter

from sonora.api.deps import DB, CurrentUser, ServicesDep
from sonora.api.schemas import CheckoutOut, CheckoutRequest, PaymentOut, UserOut
from sonora.services import billing as billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout", response_model=CheckoutOut)
async def checkout(
    body: CheckoutRequest, user: CurrentUser, db: DB, services: ServicesDep
) -> CheckoutOut:
    """Activates a plan: paid plans are charged at their catalog price with the provider
    token (402 when declined), the free plan needs no token."""
    payment = await billing_service.checkout(
        db, services, user, plan_id=body.plan, token=body.payment_token
    )
    return CheckoutOut(
        user=UserOut.model_validate(user),
        payment=PaymentOut.model_validate(payment) if payment else None,
    )


@router.post("/cancel", response_model=UserOut)
async def cancel(user: CurrentUser, db: DB, services: ServicesDep) -> UserOut:
    await billing_service.cancel(db, services, user)
    return UserOut.model_validate(user)


@router.get("/payments", response_model=list[PaymentOut])
async def payments(user: CurrentUser, db: DB) -> list[PaymentOut]:
    return [PaymentOut.model_validate(p) for p in await billing_service.history(db, user)]
