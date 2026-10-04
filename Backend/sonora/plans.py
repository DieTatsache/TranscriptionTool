"""Subscription plans and their limits.

Prices live only here: the checkout charges what this catalog says, never an amount sent
by the client. New accounts get SONORA_DEFAULT_PLAN: the free plan unless the operator
chooses otherwise ("none" = no uploads until a plan is bought; see
``sonora.services.billing``).
"""

from dataclasses import dataclass

CURRENCY = "EUR"
NO_PLAN = "none"
FREE_PLAN = "free"


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    monthly_price_cents: int
    # None = no monthly cap (uploads are still rate limited).
    monthly_session_limit: int | None
    # Longest recording; None = only the server-wide SONORA_MAX_AUDIO_MINUTES.
    max_audio_minutes: int | None = None
    # Sold through the self-service checkout.
    purchasable: bool = False


PLANS: dict[str, Plan] = {
    NO_PLAN: Plan(NO_PLAN, "No plan", 0, 0),
    # Offered (without payment) when new accounts start on it, which is the default.
    FREE_PLAN: Plan(FREE_PLAN, "Free", 0, 1, max_audio_minutes=60),
    "trainer": Plan("trainer", "Trainer", 4900, 10, purchasable=True),
    "pro": Plan("pro", "Pro", 9900, None, purchasable=True),
}


def get_plan(plan_id: str) -> Plan:
    try:
        return PLANS[plan_id]
    except KeyError:
        raise ValueError(f"Unknown plan {plan_id!r}; expected one of {sorted(PLANS)}") from None


def purchasable_plans() -> list[Plan]:
    return [plan for plan in PLANS.values() if plan.purchasable]


def offered_plans(default_plan: str) -> list[Plan]:
    """The plans users can choose: the free plan when new accounts get it, then those for sale."""
    free = [PLANS[FREE_PLAN]] if default_plan == FREE_PLAN else []
    return free + purchasable_plans()


def fallback_plan(default_plan: str) -> str:
    """Where a cancelled plan leaves the account: the free plan if it is offered."""
    return FREE_PLAN if default_plan == FREE_PLAN else NO_PLAN


def audio_limit_minutes(plan: Plan, server_limit: int) -> int:
    """Longest recording processed for this plan (never above the server-wide limit)."""
    if plan.max_audio_minutes is None:
        return server_limit
    return min(plan.max_audio_minutes, server_limit)
