"""Tests for cart tool backend flow."""

from __future__ import annotations

import unittest

from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.interfaces.mcp.tools.cart_tools import (
    AptekaCartRepository,
    InMemoryCartTokenStore,
    add_to_my_cart,
    my_cart,
)


class FakeCartRepository:
    def __init__(self) -> None:
        self.created_tokens: list[str] = []
        self.add_calls: list[tuple[str, str, int]] = []

    def create_cart(self) -> CartToken:
        token = f"token-{len(self.created_tokens) + 1}"
        self.created_tokens.append(token)
        return CartToken(access_token=token, token_type="Bearer")

    def get_cart(self, token: CartToken) -> CartSnapshot:
        quantity = len(self.add_calls)
        total = float(sum(call[2] for call in self.add_calls))
        return CartSnapshot(
            items=[
                CartItem(product_id=product_id, quantity=call_quantity)
                for _, product_id, call_quantity in self.add_calls
            ],
            count=quantity,
            total=total,
        )

    def add_item(self, token: CartToken, *, product_id: str, quantity: int) -> CartSnapshot:
        self.add_calls.append((token.access_token, product_id, quantity))
        return self.get_cart(token)


class CartToolsTests(unittest.TestCase):
    def test_my_cart_creates_session_when_missing(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()

        payload = my_cart(repository=repository, token_store=token_store)

        self.assertIn("cart_session_id", payload)
        self.assertTrue(payload["cart_created"])
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["items"], [])

    def test_my_cart_reuses_existing_session(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        first = my_cart(repository=repository, token_store=token_store)

        second = my_cart(
            cart_session_id=str(first["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(second["cart_session_id"], first["cart_session_id"])
        self.assertFalse(second["cart_created"])
        self.assertEqual(len(repository.created_tokens), 1)

    def test_add_to_my_cart_creates_session_and_adds_item(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()

        payload = add_to_my_cart(
            product_id="A12",
            quantity=2,
            repository=repository,
            token_store=token_store,
        )

        self.assertIn("cart_session_id", payload)
        self.assertTrue(payload["cart_created"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["product_id"], "A12")
        self.assertEqual(payload["items"][0]["quantity"], 2)

    def test_add_to_my_cart_rejects_invalid_quantity(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()

        with self.assertRaisesRegex(ValueError, "quantity must be greater than zero"):
            add_to_my_cart(
                product_id="A12",
                quantity=0,
                repository=repository,
                token_store=token_store,
            )

    def test_apteka_repository_create_cart_calls_expected_endpoint(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[dict[str, object]] = []

        def fake_urlopen(request, timeout: float):
            requests.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "headers": dict(request.header_items()),
                    "timeout": timeout,
                }
            )
            payload = b'{"accessToken":"token-123","tokenType":"Bearer"}'
            return FakeResponse(payload)

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = repository.create_cart()

        self.assertEqual(token.access_token, "token-123")
        self.assertEqual(token.token_type, "Bearer")
        self.assertEqual(requests[0]["url"], "https://api.apteka.md/api/v1/front/cart")
        self.assertEqual(requests[0]["method"], "GET")
        self.assertNotIn("Authorization", requests[0]["headers"])


if __name__ == "__main__":
    unittest.main()
