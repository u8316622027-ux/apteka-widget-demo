"""Tests for cart tool backend flow."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.interfaces.mcp.tools.cart_tools import (
    AptekaCartRepository,
    InMemoryCartTokenStore,
    UpstashRestCartTokenStore,
    _build_default_token_store,
    _clear_default_token_store,
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

    def test_upstash_rest_store_set_and_get_token(self) -> None:
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
            body = request.data.decode("utf-8") if request.data else ""
            requests.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "headers": dict(request.header_items()),
                    "body": body,
                    "timeout": timeout,
                }
            )

            if request.full_url.endswith("/set/cart%3Asession%3Asess-1"):
                return FakeResponse(b'{"result":"OK"}')

            if request.full_url.endswith("/get/cart%3Asession%3Asess-1"):
                return FakeResponse(
                    b'{"result":"{\\"access_token\\":\\"token-42\\",\\"token_type\\":\\"Bearer\\"}"}'
                )

            raise AssertionError(f"Unexpected URL: {request.full_url}")

        store = UpstashRestCartTokenStore(
            base_url="https://example.upstash.io",
            token="secret",
            ttl_seconds=123,
            urlopen=fake_urlopen,
        )
        store.set_token("sess-1", CartToken(access_token="token-42", token_type="Bearer"))
        restored = store.get_token("sess-1")

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.access_token, "token-42")
        self.assertEqual(restored.token_type, "Bearer")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(
            requests[0]["url"], "https://example.upstash.io/set/cart%3Asession%3Asess-1"
        )
        self.assertEqual(
            requests[0]["body"],
            '{"value":"{\\"access_token\\":\\"token-42\\",\\"token_type\\":\\"Bearer\\"}","ex":123}',
        )
        self.assertEqual(requests[1]["method"], "GET")
        self.assertEqual(
            requests[1]["url"], "https://example.upstash.io/get/cart%3Asession%3Asess-1"
        )
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(requests[1]["headers"]["Authorization"], "Bearer secret")

    def test_default_token_store_uses_upstash_env(self) -> None:
        _clear_default_token_store()
        with patch.dict(
            os.environ,
            {
                "UPSTASH_REDIS_REST_URL": "https://example.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "secret",
                "CART_TOKEN_TTL_SECONDS": "321",
            },
            clear=False,
        ):
            store = _build_default_token_store()

        self.assertIsInstance(store, UpstashRestCartTokenStore)

    def test_default_token_store_is_singleton_per_process(self) -> None:
        _clear_default_token_store()
        with patch.dict(os.environ, {}, clear=False):
            first = _build_default_token_store()
            second = _build_default_token_store()

        self.assertIs(first, second)

    def test_apteka_repository_add_item_calls_add_endpoint(self) -> None:
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
            body = request.data.decode("utf-8") if request.data else ""
            requests.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "headers": dict(request.header_items()),
                    "body": body,
                    "timeout": timeout,
                }
            )
            if request.full_url.endswith("/add"):
                return FakeResponse(b"{}")
            return FakeResponse(b'{"data":{"items":[],"count":0}}')

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")
        repository.add_item(token, product_id="17405", quantity=1)

        self.assertEqual(requests[0]["url"], "https://api.apteka.md/api/v1/front/cart/add")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(requests[0]["body"], '{"id":"17405"}')
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer tok-1")


if __name__ == "__main__":
    unittest.main()
