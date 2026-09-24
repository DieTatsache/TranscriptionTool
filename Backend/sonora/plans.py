"""Subscription plans and their limits.

Billing is not integrated yet; plans only drive quotas and what the profile page shows.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Plan:
    id: str
    name: str
    monthly_price_cents: int
    # None = no monthly cap (uploads are still rate limited).
    monthly_session_limit: int | None


PLANS: dict[str, Plan] = {
    "starter": Plan("starter", "Starter", 0, 1),
    "trainer": Plan("trainer", "Trainer", 4900, 10),
    "pro": Plan("pro", "Pro", 9900, None),
}


def get_plan(plan_id: str) -> Plan:
    try:
        return PLANS[plan_id]
    except KeyError:
        raise ValueError(f"Unknown plan {plan_id!r}; expected one of {sorted(PLANS)}") from None
