"""Tests for cart tool backend flow."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.core.config import get_settings
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


class CartToolsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()
        _clear_default_token_store()

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

    def test_add_to_my_cart_adds_item_when_quantity_omitted(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()

        payload = add_to_my_cart(
            product_id="A12",
            repository=repository,
            token_store=token_store,
        )

        self.assertIn("cart_session_id", payload)
        self.assertTrue(payload["cart_created"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(repository.add_calls, [("token-1", "A12", 1)])
        self.assertEqual(repository.update_calls, [])

    def test_add_to_my_cart_adds_multiple_units_when_quantity_provided(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        payload = add_to_my_cart(
            product_id="17405",
            quantity=2,
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(payload["count"], 1)
        self.assertEqual(repository.add_calls, [("token-1", "17405", 2)])
        self.assertEqual(repository.update_calls, [])

    def test_add_to_my_cart_deletes_item_when_quantity_zero(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        add_to_my_cart(
            product_id="17405",
            quantity=4,
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )
        payload = add_to_my_cart(
            product_id="17405",
            quantity=0,
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(payload["items"], [])
        self.assertEqual(repository.update_calls[-1], ("token-1", []))

    def test_add_to_my_cart_updates_items_list_with_merge(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        add_to_my_cart(
            product_id="16174",
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )
        payload = add_to_my_cart(
            items=[{"product_id": "20859", "quantity": 1}],
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            repository.update_calls[-1],
            ("token-1", [("16174", 1), ("20859", 1)]),
        )

    def test_add_to_my_cart_rejects_negative_quantity(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()

        with self.assertRaisesRegex(ValueError, "quantity must be greater than or equal to zero"):
            add_to_my_cart(
                product_id="A12",
                quantity=-1,
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
        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart")
        self.assertEqual(requests[0]["method"], "GET")
        self.assertNotIn("Authorization", requests[0]["headers"])

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

        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart/add")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(requests[0]["body"], '{"id":"17405"}')
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer tok-1")

    def test_apteka_repository_update_items_calls_update_endpoint(self) -> None:
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
            if request.full_url.endswith("/update"):
                return FakeResponse(b"{}")
            return FakeResponse(b'{"data":{"items":[],"count":0}}')

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")
        repository.update_items(token, items=[("17405", 2), ("20859", 1)])

        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart/update")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(
            requests[0]["body"],
            '{"items":[{"product_id":"17405","quantity":2},{"product_id":"20859","quantity":1}],"json":true}',
        )
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer tok-1")

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

    def test_upstash_rest_store_get_token_supports_nested_value_payload(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        def fake_urlopen(request, timeout: float):
            return FakeResponse(
                (
                    '{"result":"{\\"value\\":\\"{\\\\\\"access_token\\\\\\":'
                    '\\\\\\"token-99\\\\\\",\\\\\\"token_type\\\\\\":\\\\\\"Bearer\\\\\\"}\\",'
                    '\\"ex\\":604800}"}'
                ).encode("utf-8")
            )

        store = UpstashRestCartTokenStore(
            base_url="https://example.upstash.io",
            token="secret",
            ttl_seconds=123,
            urlopen=fake_urlopen,
        )
        restored = store.get_token("sess-1")

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.access_token, "token-99")
        self.assertEqual(restored.token_type, "Bearer")

    def test_default_token_store_uses_upstash_env(self) -> None:
        _clear_default_token_store()
        get_settings.cache_clear()
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
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=False):
            first = _build_default_token_store()
            second = _build_default_token_store()

        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
