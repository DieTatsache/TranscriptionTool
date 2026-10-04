"""Plan purchases (checkout), cancellation and the payment history.

Prices come from the plan catalog, never from the client, and the client only sends the
payment provider's one-time token. Payments are recorded whether they succeed or not.
With the mock provider a purchase is a single charge: there are no renewals or prorating,
and cancelling ends the plan immediately. The free plan is switched to without payment.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sonora.billing import InvalidPaymentMethod
from sonora.container import Services
from sonora.errors import Conflict, PaymentRequired, ValidationFailed
from sonora.models import ActivityType, Payment, PaymentStatus, User
from sonora.plans import CURRENCY, Plan, fallback_plan, get_plan, offered_plans
from sonora.services import activity

logger = logging.getLogger(__name__)

# Per user: also blunts "card testing" (trying stolen cards against the checkout).
CHECKOUTS_PER_HOUR = "10/hour"
HISTORY_LIMIT = 50

_DECLINE_MESSAGES = {
    "insufficient_funds": "Your card has insufficient funds.",
}


def _activate(db: AsyncSession, user: User, plan: Plan) -> None:
    user.plan = plan.id
    activity.record(db, user.id, ActivityType.PLAN_ACTIVATED, plan.name)


async def checkout(
    db: AsyncSession, services: Services, user: User, *, plan_id: str, token: str | None
) -> Payment | None:
    """Activates an offered plan: paid plans are charged with the provider token (raises
    PaymentRequired when declined), the free plan needs no payment (returns None)."""
    await services.rate_limiter.hit(
        CHECKOUTS_PER_HOUR,
        "checkout",
        str(user.id),
        message="Too many payment attempts. Please try again later.",
    )
    offered = {plan.id: plan for plan in offered_plans(services.settings.default_plan)}
    plan = offered.get(plan_id)
    if plan is None:
        raise ValidationFailed("This plan isn't available.", code="plan_not_available")

    # Lock the user row so a double submit can't pay twice (and reload the current plan).
    await db.scalar(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user.plan == plan.id:
        raise Conflict(f"You already have the {plan.name} plan.", code="already_on_plan")

    if not plan.purchasable:  # the free plan: nothing to charge
        _activate(db, user, plan)
        await db.commit()
        logger.info("plan activated user=%s plan=%s", user.id, plan.id)
        return None
    if not token:
        raise ValidationFailed(
            "Please enter your card to buy this plan.", code="invalid_payment_method"
        )

    try:
        charge = await services.payments.charge(
            token=token,
            amount_cents=plan.monthly_price_cents,
            currency=CURRENCY,
            description=f"Sonora {plan.name} plan",
        )
    except InvalidPaymentMethod:
        raise ValidationFailed(
            "The payment details are invalid. Please enter your card again.",
            code="invalid_payment_method",
        ) from None

    payment = Payment(
        user_id=user.id,
        plan=plan.id,
        amount_cents=plan.monthly_price_cents,
        currency=CURRENCY,
        status=PaymentStatus.SUCCEEDED if charge.succeeded else PaymentStatus.FAILED,
        provider=services.payments.name,
        reference=charge.reference,
        card_brand=charge.card_brand,
        card_last4=charge.card_last4,
        failure_code=None if charge.succeeded else (charge.failure_code or "declined")[:40],
    )
    db.add(payment)
    if not charge.succeeded:
        await db.commit()
        logger.info("payment declined user=%s plan=%s", user.id, plan.id)
        raise PaymentRequired(
            _DECLINE_MESSAGES.get(payment.failure_code or "", "Your card was declined."),
            details={"decline_code": payment.failure_code},
        )

    _activate(db, user, plan)
    await db.commit()
    logger.info("plan activated user=%s plan=%s", user.id, plan.id)
    return payment


async def cancel(db: AsyncSession, services: Services, user: User) -> None:
    """Ends a purchased plan immediately; the account falls back to the free plan if it is
    offered, otherwise to no plan. Free and admin-assigned plans can't be cancelled."""
    current = get_plan(user.plan)
    if not current.purchasable:
        raise Conflict("You have no plan to cancel.", code="no_active_plan")
    user.plan = fallback_plan(services.settings.default_plan)
    activity.record(db, user.id, ActivityType.PLAN_CANCELED, current.name)
    await db.commit()
    logger.info("plan cancelled user=%s plan=%s", user.id, current.id)


async def history(db: AsyncSession, user: User) -> list[Payment]:
    rows = await db.scalars(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc(), Payment.id)
        .limit(HISTORY_LIMIT)
    )
    return list(rows)
