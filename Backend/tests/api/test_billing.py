from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from sonora.billing import MOCK_TOKENS, MockPaymentProvider
from sonora.container import Services
from sonora.models import Payment, PaymentStatus
from tests.conftest import PASSWORD, Account, db_user, upload

CHECKOUT = "/api/v1/billing/checkout"


async def checkout(account: Account, plan: str = "trainer", token: str = "tok_visa") -> Any:
    return await account.client.post(CHECKOUT, json={"plan": plan, "payment_token": token})


async def activity_types(account: Account) -> list[str]:
    return [e["type"] for e in (await account.client.get("/api/v1/me/activity")).json()]


@pytest.fixture
def account_plan() -> str | None:
    return None  # fresh accounts that haven't bought anything yet (the free plan)


NO_FREE_TIER = {"default_plan": "none"}


class TestSignUp:
    async def test_new_accounts_get_one_free_session_a_month(self, account: Account) -> None:
        me = (await account.client.get("/api/v1/auth/me")).json()
        assert me["user"]["plan"] == "free"
        assert (await upload(account.client)).status_code == 202
        second = await upload(account.client)
        assert second.status_code == 403
        assert second.json()["error"]["code"] == "quota_exceeded"

    @pytest.mark.parametrize("settings_overrides", [NO_FREE_TIER])
    async def test_without_a_free_tier_new_accounts_cannot_upload(self, account: Account) -> None:
        me = (await account.client.get("/api/v1/auth/me")).json()
        assert me["user"]["plan"] == "none"
        response = await upload(account.client)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "plan_required"

    async def test_the_client_cannot_choose_its_plan(self, client: httpx.AsyncClient) -> None:
        # Regression: sign-up used to accept {"plan": "pro"} and grant it without payment.
        response = await client.post(
            "/api/v1/auth/register",
            json={"name": "N", "email": "free@example.com", "password": PASSWORD, "plan": "pro"},
        )
        assert response.status_code == 201
        assert response.json()["user"]["plan"] == "free"


class TestCheckout:
    async def test_successful_payment_activates_the_plan(
        self, account: Account, services: Services
    ) -> None:
        response = await checkout(account, "trainer", "tok_mastercard")

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["plan"] == "trainer"
        payment = body["payment"]
        assert payment["status"] == "succeeded"
        assert payment["amount_cents"] == 4900  # from the catalog, never from the client
        assert payment["currency"] == "EUR"
        assert (payment["card_brand"], payment["card_last4"]) == ("mastercard", "4444")
        assert payment["failure_code"] is None
        assert (await upload(account.client)).status_code == 202
        usage = (await account.client.get("/api/v1/me/usage")).json()
        assert usage["remaining_this_month"] == 9
        assert (await activity_types(account))[-2:] == ["plan_activated", "account_created"]
        user = await db_user(services, account.email)
        assert user.plan == "trainer"

    async def test_upgrading_charges_the_new_plan(self, account: Account) -> None:
        assert (await checkout(account, "trainer")).status_code == 200
        response = await checkout(account, "pro")
        assert response.status_code == 200
        assert response.json()["payment"]["amount_cents"] == 9900
        usage = (await account.client.get("/api/v1/me/usage")).json()
        assert usage["plan"]["id"] == "pro"
        assert usage["remaining_this_month"] is None

    async def test_buying_the_current_plan_again_is_refused(
        self, account: Account, services: Services
    ) -> None:
        assert (await checkout(account, "pro")).status_code == 200
        again = await checkout(account, "pro")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "already_on_plan"
        async with services.sessionmaker() as db:
            assert await db.scalar(select(func.count()).select_from(Payment)) == 1  # no charge

    @pytest.mark.parametrize(
        ("token", "decline_code", "message"),
        [
            ("tok_chargeDeclined", "card_declined", "Your card was declined."),
            (
                "tok_chargeDeclinedInsufficientFunds",
                "insufficient_funds",
                "Your card has insufficient funds.",
            ),
        ],
    )
    async def test_declined_payments_are_recorded_but_grant_nothing(
        self, account: Account, token: str, decline_code: str, message: str
    ) -> None:
        response = await checkout(account, "pro", token)

        assert response.status_code == 402
        error = response.json()["error"]
        assert error["code"] == "payment_declined"
        assert error["message"] == message
        assert error["details"] == {"decline_code": decline_code}
        me = (await account.client.get("/api/v1/auth/me")).json()
        assert me["user"]["plan"] == "free"  # unchanged
        (payment,) = (await account.client.get("/api/v1/billing/payments")).json()
        assert payment["status"] == "failed"
        assert payment["failure_code"] == decline_code

    @pytest.mark.parametrize(
        ("body", "status", "code"),
        [
            ({"plan": "starter", "payment_token": "tok_visa"}, 422, "plan_not_available"),
            ({"plan": "none", "payment_token": "tok_visa"}, 422, "plan_not_available"),
            ({"plan": "platinum", "payment_token": "tok_visa"}, 422, "plan_not_available"),
            ({"plan": "pro", "payment_token": "tok_made_up"}, 422, "invalid_payment_method"),
            # Card numbers are never accepted: only provider tokens (letters, digits, _ and -).
            ({"plan": "pro", "payment_token": "4242 4242 4242 4242"}, 422, "validation_error"),
            ({"plan": "pro"}, 422, "invalid_payment_method"),  # paid plans need a token
            ({"plan": "pro", "payment_token": "x" * 256}, 422, "validation_error"),
        ],
    )
    async def test_rejects_invalid_requests(
        self, account: Account, body: dict[str, Any], status: int, code: str
    ) -> None:
        response = await account.client.post(CHECKOUT, json=body)
        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert (await account.client.get("/api/v1/billing/payments")).json() == []

    @pytest.mark.parametrize("account_plan", ["none"])
    async def test_switching_to_the_free_plan_needs_no_payment(
        self, account: Account, services: Services
    ) -> None:
        response = await account.client.post(CHECKOUT, json={"plan": "free"})

        assert response.status_code == 200
        assert response.json() == {"user": response.json()["user"], "payment": None}
        assert response.json()["user"]["plan"] == "free"
        assert (await activity_types(account))[0] == "plan_activated"
        async with services.sessionmaker() as db:
            assert await db.scalar(select(func.count()).select_from(Payment)) == 0
        again = await account.client.post(CHECKOUT, json={"plan": "free"})
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "already_on_plan"

    @pytest.mark.parametrize("settings_overrides", [NO_FREE_TIER])
    async def test_the_free_plan_is_not_offered_without_a_free_tier(self, account: Account) -> None:
        response = await account.client.post(CHECKOUT, json={"plan": "free"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "plan_not_available"
        me = (await account.client.get("/api/v1/auth/me")).json()
        assert me["user"]["plan"] == "none"

    async def test_requires_sign_in_and_csrf(self, account: Account, client_factory: Any) -> None:
        async with client_factory() as anonymous:
            response = await anonymous.post(
                CHECKOUT, json={"plan": "pro", "payment_token": "tok_visa"}
            )
        assert response.status_code == 401
        del account.client.headers["X-CSRF-Token"]
        response = await checkout(account, "pro")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_failed"

    async def test_attempts_are_rate_limited(self, account: Account) -> None:
        # Blunts "card testing": trying many cards against the checkout.
        for _ in range(10):
            assert (await checkout(account, "pro", "tok_chargeDeclined")).status_code == 402
        limited = await checkout(account, "pro", "tok_visa")
        assert limited.status_code == 429


class TestCancelAndHistory:
    async def test_cancelling_falls_back_to_the_free_plan(self, account: Account) -> None:
        await checkout(account, "trainer")

        response = await account.client.post("/api/v1/billing/cancel")

        assert response.status_code == 200
        assert response.json()["plan"] == "free"
        usage = (await account.client.get("/api/v1/me/usage")).json()
        assert usage["plan"]["monthly_session_limit"] == 1
        assert (await activity_types(account))[0] == "plan_canceled"
        # The free plan itself can't be cancelled.
        again = await account.client.post("/api/v1/billing/cancel")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "no_active_plan"

    @pytest.mark.parametrize("settings_overrides", [NO_FREE_TIER])
    async def test_without_a_free_tier_cancelling_ends_uploads(self, account: Account) -> None:
        await checkout(account, "trainer")

        response = await account.client.post("/api/v1/billing/cancel")

        assert response.json()["plan"] == "none"
        assert (await upload(account.client)).json()["error"]["code"] == "plan_required"

    @pytest.mark.parametrize("account_plan", ["none"])
    async def test_accounts_without_a_plan_have_nothing_to_cancel(self, account: Account) -> None:
        response = await account.client.post("/api/v1/billing/cancel")
        assert response.status_code == 409

    async def test_history_is_newest_first_and_private(
        self, account: Account, other_account: Account
    ) -> None:
        await checkout(account, "trainer", "tok_chargeDeclined")
        await checkout(account, "trainer")
        await checkout(other_account, "pro")

        history = (await account.client.get("/api/v1/billing/payments")).json()

        assert [(p["plan"], p["status"]) for p in history] == [
            ("trainer", "succeeded"),
            ("trainer", "failed"),
        ]
        assert set(history[0]) == {
            "id",
            "plan",
            "amount_cents",
            "currency",
            "status",
            "card_brand",
            "card_last4",
            "failure_code",
            "created_at",
        }

    async def test_payments_are_erased_with_the_account(
        self, account: Account, services: Services
    ) -> None:
        await checkout(account, "pro")
        response = await account.client.post("/api/v1/me/delete", json={"password": PASSWORD})
        assert response.status_code == 204
        async with services.sessionmaker() as db:
            assert await db.scalar(select(func.count()).select_from(Payment)) == 0


async def test_mock_provider_knows_only_its_test_tokens() -> None:
    provider = MockPaymentProvider()
    assert provider.name == "mock"
    ok = await provider.charge(token="tok_visa", amount_cents=100, currency="EUR", description="x")
    assert ok.succeeded and ok.reference.startswith("mock_") and ok.card_last4 == "4242"
    declined = await provider.charge(
        token="tok_chargeDeclined", amount_cents=100, currency="EUR", description="x"
    )
    assert not declined.succeeded and declined.failure_code == "card_declined"
    assert {"tok_visa", "tok_mastercard"} <= set(MOCK_TOKENS)
    assert PaymentStatus.SUCCEEDED.value == "succeeded"
