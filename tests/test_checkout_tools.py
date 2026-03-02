"""Tests for checkout tool backend flow."""

from __future__ import annotations

import unittest

from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.interfaces.mcp.tools.cart_tools import InMemoryCartTokenStore, add_to_my_cart, my_cart
from app.interfaces.mcp.tools.checkout_tools import (
    AptekaCheckoutReferenceRepository,
    _clear_checkout_reference_cache,
    checkout_order,
)


class FakeCartRepository:
    def __init__(self) -> None:
        self.created_tokens: list[str] = []
        self.add_calls: list[tuple[str, str, int]] = []
        self.update_calls: list[tuple[str, list[tuple[str, int]]]] = []

    def create_cart(self) -> CartToken:
        token = f"token-{len(self.created_tokens) + 1}"
        self.created_tokens.append(token)
        return CartToken(access_token=token, token_type="Bearer")

    def get_cart(self, token: CartToken) -> CartSnapshot:
        quantities: dict[str, int] = {}
        for _, product_id, quantity in self.add_calls:
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        for _, updates in self.update_calls:
            quantities = {product_id: quantity for product_id, quantity in updates}

        items = [
            CartItem(product_id=product_id, quantity=quantity)
            for product_id, quantity in quantities.items()
            if quantity > 0
        ]
        return CartSnapshot(items=items, count=len(items), total=float(sum(quantities.values())))

    def add_item(self, token: CartToken, *, product_id: str, quantity: int) -> CartSnapshot:
        self.add_calls.append((token.access_token, product_id, quantity))
        return self.get_cart(token)

    def update_items(self, token: CartToken, *, items: list[tuple[str, int]]) -> CartSnapshot:
        self.update_calls.append((token.access_token, items))
        return self.get_cart(token)


class FakeCheckoutReferenceRepository:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_regions(self) -> list[dict[str, object]]:
        self.calls.append("regions")
        return [{"id": 1}]

    def get_cities_without_regions(self) -> list[dict[str, object]]:
        self.calls.append("cities_without_regions")
        return [{"id": 2}]

    def get_pharmacies(self) -> list[dict[str, object]]:
        self.calls.append("pharmacies")
        return [{"id": 3}]


class CheckoutToolsTests(unittest.TestCase):
    def tearDown(self) -> None:
        _clear_checkout_reference_cache()

    def test_checkout_order_returns_friendly_message_when_cart_is_empty(self) -> None:
        cart_repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        reference_repository = FakeCheckoutReferenceRepository()

        payload = checkout_order(
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "cart_empty")
        self.assertIn("корзин", str(payload["message"]).lower())
        self.assertIn("cart_session_id", payload)
        self.assertEqual(reference_repository.calls, [])

    def test_checkout_order_prefetches_reference_data_and_returns_delivery_step(self) -> None:
        cart_repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        reference_repository = FakeCheckoutReferenceRepository()
        session = my_cart(repository=cart_repository, token_store=token_store)
        add_to_my_cart(
            product_id="17405",
            cart_session_id=str(session["cart_session_id"]),
            repository=cart_repository,
            token_store=token_store,
        )

        payload = checkout_order(
            cart_session_id=str(session["cart_session_id"]),
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "delivery_method_selection")
        self.assertEqual(payload["cart_count"], 1)
        self.assertEqual(len(payload["delivery_options"]), 2)
        self.assertEqual(
            reference_repository.calls,
            ["regions", "cities_without_regions", "pharmacies"],
        )

    def test_checkout_order_uses_cached_reference_data_between_calls(self) -> None:
        cart_repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        reference_repository = FakeCheckoutReferenceRepository()
        session = my_cart(repository=cart_repository, token_store=token_store)
        add_to_my_cart(
            product_id="17405",
            cart_session_id=str(session["cart_session_id"]),
            repository=cart_repository,
            token_store=token_store,
        )

        checkout_order(
            cart_session_id=str(session["cart_session_id"]),
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )
        checkout_order(
            cart_session_id=str(session["cart_session_id"]),
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(
            reference_repository.calls,
            ["regions", "cities_without_regions", "pharmacies"],
        )

    def test_checkout_reference_repository_calls_all_expected_get_endpoints(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[tuple[str, str]] = []

        def fake_urlopen(request, timeout: float):
            del timeout
            requests.append((request.full_url, request.get_method()))
            return FakeResponse(b'{"data":[{"id":1}]}')

        repository = AptekaCheckoutReferenceRepository(urlopen=fake_urlopen)

        repository.get_regions()
        repository.get_cities_without_regions()
        repository.get_pharmacies()

        self.assertEqual(
            requests,
            [
                ("https://stage.apteka.md/api/v1/front//regions", "GET"),
                ("https://stage.apteka.md/api/v1/front//cities-without-regions", "GET"),
                ("https://stage.apteka.md/api/v1/front//pharmacies/new-list", "GET"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
