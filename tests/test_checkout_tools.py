"""Checkout must review the authenticated cart before creating a real order."""

from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.domain.cart.service import _SESSION_LOCKS
from app.interfaces.mcp.tools import checkout_api, checkout_tools
from app.interfaces.mcp.tools.cart_tools import InMemoryCartTokenStore


class CartRepository:
    def __init__(self):
        self.snapshot = CartSnapshot(
            items=[CartItem(product_id="101", quantity=2, name="Test", price=Decimal("40"))],
            count=2,
            total=Decimal("80"),
        )

    def get_cart(self, token):
        assert token.access_token == "private-token"
        return self.snapshot


class CheckoutClient:
    def __init__(self):
        self.orders = []

    def reference_data(self, language):
        return {
            "regions": [{"id": 2, "name": "Chisinau", "delivery_cost": 30}],
            "cities": [{"id": 24, "region_id": 2, "name": "Ciocana"}],
            "pharmacies": [
                {"id": 1, "region_id": 2, "city_id": 24, "name": "Farmacia", "address": "Street 1"}
            ],
        }

    def delivery_windows(self, method, destination_id, language):
        return [{"deliveryDate": "03.11.2026", "from": "13:00", "to": "15:00"}]

    def send_order(self, token, payload, language):
        self.orders.append((token.access_token, payload))
        return {"id": 123, "number": "AP-123"}


@pytest.fixture
def checkout():
    store = InMemoryCartTokenStore()
    store.set_token("session-a", CartToken("private-token", "Bearer"))
    repository = CartRepository()
    client = CheckoutClient()

    def call(**arguments):
        return checkout_tools.checkout_order(
            {"cart_session_id": "session-a", **arguments},
            repository=repository,
            token_store=store,
            client=client,
        )

    return call, repository, client


def review_arguments(**overrides):
    return {
        "action": "review",
        "delivery_method": "pickup",
        "pharmacy_id": 1,
        "contact": {"first_name": "Ana", "phone": "+37379802000"},
        "payment_method": "cash_on_receipt",
        **overrides,
    }


def test_options_do_not_submit_and_hide_private_token(checkout):
    call, _, client = checkout
    result = call()
    assert result["status"] == "delivery_method_selection"
    assert result["pharmacies"][0]["id"] == 1
    assert "private-token" not in str(result)
    assert client.orders == []


def test_delivery_step_returns_windows_without_requiring_contact(checkout):
    call, _, client = checkout
    result = call(action="delivery", delivery_method="pickup", pharmacy_id=1)
    assert result["status"] == "delivery_windows"
    assert result["windows"][0]["deliveryDate"] == "03.11.2026"
    assert not client.orders


def test_courier_calculates_delivery_for_selected_region(checkout):
    call, _, client = checkout
    destinations = []
    original = client.delivery_windows

    def windows(method, destination_id, language):
        destinations.append(destination_id)
        return original(method, destination_id, language)

    client.delivery_windows = windows
    call(
        **review_arguments(
            delivery_method="courier",
            region_id=2,
            city_id=24,
            address={"street": "Dacia", "house_number": "10"},
        )
    )
    assert destinations == [2]


def test_pickup_review_submit_uses_same_cart_and_is_idempotent(checkout):
    call, _, client = checkout
    review = call(**review_arguments())
    assert review["status"] == "review"
    assert review["review"]["total"] == 80
    assert review["review"]["checkout_input"]["pharmacy_id"] == 1
    assert not client.orders
    arguments = dict(
        action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True
    )
    result = call(**arguments)
    assert result["status"] == "order_submitted"
    assert call(**arguments) == result
    assert len(client.orders) == 1
    token, order = client.orders[0]
    assert token == "private-token"
    assert order["delivery"]["type"] == "pick-up"
    assert order["delivery"]["pharmacy_id"] == 1
    assert order["payment"]["type"] == "cash"


@pytest.mark.parametrize("payment,wire", [("cash_on_receipt", "cash"), ("card_on_receipt", "card")])
@pytest.mark.parametrize("delivery_method", ["pickup", "courier"])
def test_api_receives_supported_payment_values(checkout, payment, wire, delivery_method):
    call, _, client = checkout
    review = call(
        **review_arguments(
            payment_method=payment,
            delivery_method=delivery_method,
            region_id=2,
            city_id=24,
            address={"street": "Dacia", "house_number": "10"},
        )
    )
    assert review["review"]["payment_method"] == payment
    call(action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True)
    assert client.orders[0][1]["payment"]["type"] == wire


def test_explicit_validation_rejection_allows_manual_retry_without_automatic_retry(checkout):
    call, _, client = checkout
    review = call(**review_arguments())
    calls = []

    def send(token, payload, language):
        calls.append(payload)
        if len(calls) == 1:
            raise checkout_api.OrderValidationError(["payment.type"], language=language)
        return {"id": 123, "number": "AP-123"}

    client.send_order = send
    args = dict(action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True)
    with pytest.raises(ValueError, match="оплат"):
        call(**args)
    assert len(calls) == 1
    result = call(**args)
    assert result["status"] == "order_submitted"
    assert call(**args) == result
    assert len(calls) == 2


def test_server_error_keeps_status_uncertain_and_prevents_resubmission(checkout):
    call, _, client = checkout
    review = call(**review_arguments())
    calls = []

    def send(*_):
        calls.append(True)
        raise ValueError("Apteka API request failed (HTTP 500)")

    client.send_order = send
    args = dict(action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True)
    with pytest.raises(ValueError, match="500"):
        call(**args)
    with pytest.raises(ValueError, match="status"):
        call(**args)
    assert len(calls) == 1


def test_courier_review_has_selected_destination_and_shipping(checkout):
    call, _, client = checkout
    result = call(
        **review_arguments(
            delivery_method="courier",
            region_id=2,
            city_id=24,
            address={"street": "Dacia", "house_number": "10", "apartment": "2"},
        )
    )
    assert result["review"]["delivery_fee"] == 30
    assert result["review"]["total"] == 110
    call(action="submit", confirmation_id=result["confirmation_id"], terms_accepted=True)
    address = client.orders[0][1]["delivery"]["address"]
    assert address["region_id"] == 2
    assert address["sector_id"] == 24
    assert address["building"] == "10"


@pytest.mark.parametrize(
    "change",
    [
        {"pharmacy_id": 999},
        {"contact": {"first_name": "A", "phone": "123"}},
        {"delivery_method": "courier", "region_id": 2, "city_id": 999},
        {"payment_method": "invented"},
    ],
)
def test_review_rejects_invalid_input_before_order(checkout, change):
    call, _, client = checkout
    with pytest.raises(ValueError):
        call(**review_arguments(**change))
    assert not client.orders


def test_submit_requires_review_and_explicit_terms(checkout):
    call, _, client = checkout
    with pytest.raises(ValueError):
        call(action="submit", terms_accepted=True)
    review = call(**review_arguments())
    with pytest.raises(ValueError):
        call(action="submit", confirmation_id=review["confirmation_id"])
    assert not client.orders


def test_cart_changes_invalidate_review(checkout):
    call, repository, client = checkout
    review = call(**review_arguments())
    repository.snapshot.items[0] = replace(repository.snapshot.items[0], quantity=3)
    with pytest.raises(ValueError, match="cart.*changed"):
        call(action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True)
    assert not client.orders


def test_cart_mutations_cannot_interleave_with_submission(checkout):
    call, _, client = checkout
    review = call(**review_arguments())
    original = client.send_order

    def submit(token, payload, language):
        assert _SESSION_LOCKS["session-a"].lock.locked()
        return original(token, payload, language)

    client.send_order = submit
    call(action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True)


def test_confirmation_cannot_be_used_by_another_session(checkout):
    call, _, client = checkout
    review = call(**review_arguments())
    with pytest.raises(ValueError):
        call(
            action="submit",
            cart_session_id="session-b",
            confirmation_id=review["confirmation_id"],
            terms_accepted=True,
        )
    assert not client.orders


def test_empty_cart_cannot_be_reviewed(checkout):
    call, repository, client = checkout
    repository.snapshot = CartSnapshot(items=[], count=0, total=Decimal("0"))
    result = call(**review_arguments())
    assert result["status"] == "cart_empty"
    assert not client.orders


def test_failure_does_not_report_success_or_retry_order(checkout):
    call, _, client = checkout
    review = call(**review_arguments())

    def fail(*_):
        raise TimeoutError("network")

    client.send_order = fail
    args = dict(action="submit", confirmation_id=review["confirmation_id"], terms_accepted=True)
    with pytest.raises(TimeoutError):
        call(**args)
    with pytest.raises(ValueError, match="status"):
        call(**args)
