"""Payment providers behind the ``PaymentProvider`` protocol.

Like with real card processors, the browser collects card details in the provider's own
form and the API only ever receives a one-time token: card numbers never reach this
server. The only provider so far is a simulation that understands Stripe-style test
tokens; a real provider can be added behind the same protocol.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sonora.config import BillingProvider, Settings


class InvalidPaymentMethod(Exception):
    """The provider doesn't know the token (made up, expired or already used)."""


@dataclass(frozen=True, slots=True)
class Charge:
    reference: str
    succeeded: bool
    card_brand: str | None = None
    card_last4: str | None = None
    # Provider decline code when not succeeded, e.g. "card_declined".
    failure_code: str | None = None


class PaymentProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def charge(
        self, *, token: str, amount_cents: int, currency: str, description: str
    ) -> Charge: ...


# Test token -> (card brand, last four digits, decline code).
MOCK_TOKENS: dict[str, tuple[str, str, str | None]] = {
    "tok_visa": ("visa", "4242", None),
    "tok_mastercard": ("mastercard", "4444", None),
    "tok_chargeDeclined": ("visa", "0002", "card_declined"),
    "tok_chargeDeclinedInsufficientFunds": ("visa", "9995", "insufficient_funds"),
}


class MockPaymentProvider:
    """Simulated card processor: accepts only the test tokens above and moves no money."""

    @property
    def name(self) -> str:
        return BillingProvider.MOCK.value

    async def charge(
        self, *, token: str, amount_cents: int, currency: str, description: str
    ) -> Charge:
        try:
            brand, last4, failure = MOCK_TOKENS[token]
        except KeyError:
            raise InvalidPaymentMethod("unknown payment token") from None
        return Charge(
            reference=f"mock_{uuid.uuid4().hex}",
            succeeded=failure is None,
            card_brand=brand,
            card_last4=last4,
            failure_code=failure,
        )


def build_payment_provider(settings: Settings) -> PaymentProvider:
    # One provider so far; a real one would be selected here by settings.billing_provider.
    del settings
    return MockPaymentProvider()
