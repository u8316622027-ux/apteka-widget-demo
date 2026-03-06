"""Tests for cart tool backend flow."""

from __future__ import annotations

import os
import threading
import time
import unittest
from decimal import Decimal
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from app.core.config import get_settings
from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.domain.cart.service import _SESSION_LOCKS
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
        self._quantities: dict[str, int] = {}

    def create_cart(self) -> CartToken:
        token = f"token-{len(self.created_tokens) + 1}"
        self.created_tokens.append(token)
        return CartToken(access_token=token, token_type="Bearer")

    def get_cart(self, token: CartToken) -> CartSnapshot:
        items = [
            CartItem(product_id=product_id, quantity=quantity)
            for product_id, quantity in self._quantities.items()
            if quantity > 0
        ]
        return CartSnapshot(items=items, count=len(items), total=float(sum(self._quantities.values())))

    def add_item(
        self,
        token: CartToken,
        *,
        product_id: str,
        quantity: int,
        item_meta: dict[str, object] | None = None,
    ) -> CartSnapshot:
        del item_meta
        self._quantities[product_id] = self._quantities.get(product_id, 0) + quantity
        self.add_calls.append((token.access_token, product_id, quantity))
        return self.get_cart(token)

    def update_items(
        self,
        token: CartToken,
        *,
        items: list[tuple[str, int]],
        item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
    ) -> CartSnapshot:
        del item_meta_by_product_id
        self._quantities = {
            product_id: quantity for product_id, quantity in items if quantity > 0
        }
        self.update_calls.append((token.access_token, items))
        return self.get_cart(token)


class CartToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._base_url_patcher = patch.dict(
            os.environ,
            {"APTEKA_BASE_URL": "https://stage.apteka.md"},
            clear=False,
        )
        self._base_url_patcher.start()
        self.addCleanup(self._base_url_patcher.stop)

    def tearDown(self) -> None:
        get_settings.cache_clear()
        _clear_default_token_store()
        _SESSION_LOCKS.clear()

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

    def test_my_cart_keeps_explicit_session_id_when_token_is_created(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        explicit_session_id = "88cd64b0df112278d7e5c1a3967e4cb6258e2928ecaf8782ac47bfba0d31fd0e"

        first = my_cart(
            cart_session_id=explicit_session_id,
            repository=repository,
            token_store=token_store,
        )
        second = my_cart(
            cart_session_id=explicit_session_id,
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(first["cart_session_id"], explicit_session_id)
        self.assertTrue(first["cart_created"])
        self.assertEqual(second["cart_session_id"], explicit_session_id)
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
        self.assertEqual(repository.add_calls, [])
        self.assertEqual(repository.update_calls, [("token-1", [("A12", 1)])])

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
        self.assertEqual(repository.add_calls, [])
        self.assertEqual(repository.update_calls, [("token-1", [("17405", 2)])])

    def test_add_to_my_cart_uses_add_endpoint_when_requested(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        payload = add_to_my_cart(
            product_id="17405",
            use_add_endpoint=True,
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(payload["count"], 1)
        self.assertEqual(repository.add_calls, [("token-1", "17405", 1)])
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

    def test_add_to_my_cart_updates_only_changed_items(self) -> None:
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

    def test_add_to_my_cart_sends_meta_only_for_changed_items(self) -> None:
        class MetadataRepository:
            def __init__(self) -> None:
                self.last_item_meta_by_product_id: dict[str, dict[str, object]] | None = None

            def create_cart(self) -> CartToken:
                return CartToken(access_token="token-1", token_type="Bearer")

            def get_cart(self, token: CartToken) -> CartSnapshot:
                del token
                return CartSnapshot(
                    items=[
                        CartItem(
                            product_id="16174",
                            quantity=1,
                            name="Ибупрофен",
                            price=10.0,
                            discount_price=9.5,
                            manufacturer="Bayer",
                        )
                    ],
                    count=1,
                    total=10.0,
                )

            def add_item(
                self,
                token: CartToken,
                *,
                product_id: str,
                quantity: int,
                item_meta: dict[str, object] | None = None,
            ) -> CartSnapshot:
                del token, product_id, quantity, item_meta
                raise AssertionError("add_item should not be used in this scenario")

            def update_items(
                self,
                token: CartToken,
                *,
                items: list[tuple[str, int]],
                item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
            ) -> CartSnapshot:
                del token, items
                self.last_item_meta_by_product_id = item_meta_by_product_id
                return CartSnapshot(items=[], count=0, total=None)

        repository = MetadataRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        add_to_my_cart(
            items=[
                {
                    "product_id": "20750",
                    "quantity": 1,
                    "name": "Нурофен",
                    "price": 12.0,
                    "discount_price": 11.0,
                    "manufacturer": "Reckitt",
                }
            ],
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertIsNotNone(repository.last_item_meta_by_product_id)
        assert repository.last_item_meta_by_product_id is not None
        self.assertIn("16174", repository.last_item_meta_by_product_id)
        self.assertEqual(
            repository.last_item_meta_by_product_id["20750"],
            {
                "name": "Нурофен",
                "manufacturer": "Reckitt",
                "price": 12.0,
                "discount_price": 11.0,
            },
        )
        self.assertEqual(
            repository.last_item_meta_by_product_id["16174"]["manufacturer"],
            "Bayer",
        )

    def test_add_to_my_cart_collapses_duplicate_items_to_last_value(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        payload = add_to_my_cart(
            items=[
                {"product_id": "16174", "quantity": 1},
                {"product_id": "16174", "quantity": 3},
                {"product_id": "20859", "quantity": 2},
            ],
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(payload["count"], 2)
        self.assertEqual(
            repository.update_calls[-1],
            ("token-1", [("16174", 3), ("20859", 2)]),
        )

    def test_add_to_my_cart_serializes_batch_updates_per_session(self) -> None:
        class ConcurrentRepository:
            def __init__(self) -> None:
                self._lock = threading.Lock()
                self.concurrent = 0
                self.max_concurrent = 0
                self.state: dict[str, int] = {}

            def create_cart(self) -> CartToken:
                return CartToken(access_token="token-1", token_type="Bearer")

            def get_cart(self, token: CartToken) -> CartSnapshot:
                with self._lock:
                    items = [
                        CartItem(product_id=product_id, quantity=quantity)
                        for product_id, quantity in self.state.items()
                    ]
                return CartSnapshot(items=items, count=len(items), total=float(len(items)))

            def add_item(
                self,
                token: CartToken,
                *,
                product_id: str,
                quantity: int,
                item_meta: dict[str, object] | None = None,
            ) -> CartSnapshot:
                del item_meta
                with self._lock:
                    self.state[product_id] = self.state.get(product_id, 0) + quantity
                return self.get_cart(token)

            def update_items(
                self,
                token: CartToken,
                *,
                items: list[tuple[str, int]],
                item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
            ) -> CartSnapshot:
                del item_meta_by_product_id
                with self._lock:
                    self.concurrent += 1
                    if self.concurrent > self.max_concurrent:
                        self.max_concurrent = self.concurrent
                try:
                    time.sleep(0.03)
                    with self._lock:
                        for product_id, quantity in items:
                            if quantity <= 0:
                                self.state.pop(product_id, None)
                            else:
                                self.state[product_id] = quantity
                finally:
                    with self._lock:
                        self.concurrent -= 1
                return self.get_cart(token)

        repository = ConcurrentRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)
        session_id = str(session["cart_session_id"])
        barrier = threading.Barrier(3)
        errors: list[Exception] = []

        def worker(product_id: str) -> None:
            try:
                barrier.wait(timeout=1)
                add_to_my_cart(
                    items=[{"product_id": product_id, "quantity": 1}],
                    cart_session_id=session_id,
                    repository=repository,
                    token_store=token_store,
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread1 = threading.Thread(target=worker, args=("16174",))
        thread2 = threading.Thread(target=worker, args=("20859",))
        thread1.start()
        thread2.start()
        barrier.wait(timeout=1)
        thread1.join(timeout=1)
        thread2.join(timeout=1)

        self.assertEqual(errors, [])
        self.assertEqual(repository.max_concurrent, 1)

    def test_add_to_my_cart_releases_session_lock_after_batch_update(self) -> None:
        repository = FakeCartRepository()
        token_store = InMemoryCartTokenStore()
        session = my_cart(repository=repository, token_store=token_store)

        add_to_my_cart(
            items=[{"product_id": "16174", "quantity": 1}],
            cart_session_id=str(session["cart_session_id"]),
            repository=repository,
            token_store=token_store,
        )

        self.assertEqual(_SESSION_LOCKS, {})

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

    def test_apteka_repository_add_item_uses_add_endpoint(self) -> None:
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
        repository.add_item(
            token,
            product_id="17405",
            quantity=5,
            item_meta={
                "name": "Aspirin Cardio",
                "price": 31.17,
                "discount_price": 29.99,
                "manufacturer": "Bayer",
                "image_url": "https://cdn.example.com/aspirin.png",
            },
        )

        self.assertEqual(
            requests[0]["url"],
            "https://stage.apteka.md/api/v1/front/cart/add",
        )
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(
            requests[0]["body"],
            '{"product_id":"17405","quantity":5,"json":true,"name":"Aspirin Cardio","manufacturer":"Bayer","price":31.17,"discount_price":29.99,"image_url":"https://cdn.example.com/aspirin.png"}',
        )
        self.assertEqual(requests[0]["headers"]["Authorization"], "Bearer tok-1")
        self.assertEqual(
            requests[1]["url"],
            "https://stage.apteka.md/api/v1/front/cart",
        )
        self.assertEqual(requests[1]["method"], "GET")

    def test_apteka_repository_add_item_does_not_fetch_cart_before_add(self) -> None:
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
                    "body": body,
                    "timeout": timeout,
                }
            )
            if request.full_url.endswith("/add"):
                return FakeResponse(b"{}")
            return FakeResponse(b'{"data":{"items":[],"count":0}}')

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")
        repository.add_item(
            token,
            product_id="20750",
            quantity=1,
            item_meta={
                "name": "Nurofen",
                "price": 30.0,
                "discount_price": 25.0,
                "manufacturer": "Reckitt",
            },
        )

        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart/add")
        self.assertEqual(
            requests[0]["body"],
            '{"product_id":"20750","quantity":1,"json":true,"name":"Nurofen","manufacturer":"Reckitt","price":30.0,"discount_price":25.0}',
        )

    def test_apteka_repository_add_item_falls_back_to_update_when_add_fails(self) -> None:
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
                    "body": body,
                    "timeout": timeout,
                }
            )
            if request.full_url.endswith("/add"):
                raise HTTPError(request.full_url, 409, "Conflict", hdrs=None, fp=None)
            if request.full_url.endswith("/update"):
                return FakeResponse(b"{}")
            return FakeResponse(
                b'{"data":{"items":[{"product_id":"17405","quantity":1}],"count":1}}'
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")
        repository.add_item(token, product_id="17405", quantity=1)

        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart/add")
        self.assertEqual(requests[1]["url"], "https://stage.apteka.md/api/v1/front/cart")
        self.assertEqual(requests[2]["url"], "https://stage.apteka.md/api/v1/front/cart/update")
        self.assertEqual(
            requests[2]["body"],
            '{"items":[{"product_id":"17405","quantity":2}],"json":true}',
        )

    def test_apteka_repository_add_item_falls_back_to_update_when_add_returns_400(self) -> None:
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
                    "body": body,
                    "timeout": timeout,
                }
            )
            if request.full_url.endswith("/add"):
                raise HTTPError(request.full_url, 400, "Bad Request", hdrs=None, fp=None)
            if request.full_url.endswith("/update"):
                return FakeResponse(b"{}")
            return FakeResponse(
                b'{"data":{"items":[{"product_id":"17405","quantity":1}],"count":1}}'
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")
        repository.add_item(token, product_id="17405", quantity=1)

        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart/add")
        self.assertEqual(requests[1]["url"], "https://stage.apteka.md/api/v1/front/cart")
        self.assertEqual(requests[2]["url"], "https://stage.apteka.md/api/v1/front/cart/update")

    def test_apteka_repository_add_item_fallback_preserves_other_items(self) -> None:
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
                    "body": body,
                    "timeout": timeout,
                }
            )
            if request.full_url.endswith("/add"):
                raise HTTPError(request.full_url, 409, "Conflict", hdrs=None, fp=None)
            if request.full_url.endswith("/update"):
                return FakeResponse(b"{}")
            return FakeResponse(
                (
                    '{"data":{"items":['
                    '{"product_id":"16174","quantity":2,"name":"Ибупрофен","price":10.0,"discount_price":9.5,"manufacturer":"Bayer","image_url":"https://cdn.example.com/ibuprofen.png"},'
                    '{"product_id":"17405","quantity":1,"name":"Нурофен","price":12.0,"discount_price":11.0,"manufacturer":"Reckitt","image_url":"https://cdn.example.com/nurofen.png"}'
                    '],"count":2}}'
                ).encode("utf-8")
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")
        repository.add_item(
            token,
            product_id="17405",
            quantity=1,
            item_meta={
                "name": "Нурофен",
                "price": 12.0,
                "discount_price": 11.0,
                "manufacturer": "Reckitt",
                "image_url": "https://cdn.example.com/nurofen.png",
            },
        )

        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/cart/add")
        self.assertEqual(requests[1]["url"], "https://stage.apteka.md/api/v1/front/cart")
        self.assertEqual(requests[2]["url"], "https://stage.apteka.md/api/v1/front/cart/update")
        self.assertEqual(
            requests[2]["body"],
            (
                '{"items":['
                '{"product_id":"16174","quantity":2,"name":"Ибупрофен","manufacturer":"Bayer","price":10.0,"discount_price":9.5,"image_url":"https://cdn.example.com/ibuprofen.png"},'
                '{"product_id":"17405","quantity":2,"name":"Нурофен","manufacturer":"Reckitt","price":12.0,"discount_price":11.0,"image_url":"https://cdn.example.com/nurofen.png"}'
                '],"json":true}'
            ),
        )

    def test_apteka_repository_add_item_does_not_fallback_on_server_error(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[str] = []

        def fake_urlopen(request, timeout: float):
            del timeout
            requests.append(request.full_url)
            if request.full_url.endswith("/add"):
                raise HTTPError(request.full_url, 500, "Server Error", hdrs=None, fp=None)
            return FakeResponse(b"{}")

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        token = CartToken(access_token="tok-1", token_type="Bearer")

        with self.assertRaises(HTTPError):
            repository.add_item(token, product_id="17405", quantity=1)

        self.assertEqual(requests, ["https://stage.apteka.md/api/v1/front/cart/add"])

    def test_apteka_repository_maps_item_meta_from_cart_response(self) -> None:
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
            del timeout
            del request
            return FakeResponse(
                b'{"data":{"items":[{"product_id":"17405","quantity":1,"name":"Aspirin Cardio","price":31.17,"discount_price":29.99,"manufacturer":"Bayer","image_url":"https://cdn.example.com/aspirin.png"}],"count":1}}'
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        snapshot = repository.get_cart(CartToken(access_token="tok-1", token_type="Bearer"))

        self.assertEqual(snapshot.count, 1)
        self.assertEqual(snapshot.items[0].product_id, "17405")
        self.assertEqual(snapshot.items[0].quantity, 1)
        self.assertEqual(snapshot.items[0].name, "Aspirin Cardio")
        self.assertEqual(snapshot.items[0].price, Decimal("31.17"))
        self.assertEqual(snapshot.items[0].discount_price, Decimal("29.99"))
        self.assertEqual(snapshot.items[0].manufacturer, "Bayer")
        self.assertEqual(snapshot.items[0].image_url, "https://cdn.example.com/aspirin.png")
        self.assertEqual(snapshot.total, Decimal("29.99"))

    def test_apteka_repository_maps_prices_to_decimal(self) -> None:
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
            del timeout
            del request
            return FakeResponse(
                b'{"data":{"items":[{"product_id":"17405","quantity":1,"price":31.17,"discount_price":29.99}],"count":1}}'
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        snapshot = repository.get_cart(CartToken(access_token="tok-1", token_type="Bearer"))

        self.assertIsInstance(snapshot.items[0].price, Decimal)
        self.assertIsInstance(snapshot.items[0].discount_price, Decimal)
        self.assertIsInstance(snapshot.total, Decimal)

    def test_apteka_repository_computes_total_from_items_when_missing(self) -> None:
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
            del timeout
            del request
            return FakeResponse(
                (
                    '{"data":{"items":['
                    '{"product_id":"17405","quantity":2,"price":31.17,"discount_price":29.99},'
                    '{"product_id":"20750","quantity":1,"price":12.0}'
                    '],"count":2}}'
                ).encode("utf-8")
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        snapshot = repository.get_cart(CartToken(access_token="tok-1", token_type="Bearer"))

        self.assertEqual(snapshot.count, 2)
        self.assertEqual(snapshot.total, Decimal("71.98"))

    def test_apteka_repository_filters_unsafe_image_urls(self) -> None:
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
            del timeout
            del request
            return FakeResponse(
                (
                    '{"data":{"items":['
                    '{"product_id":"17405","quantity":1,"image_url":"javascript:alert(1)"},'
                    '{"product_id":"20750","quantity":1,"image_url":"https://cdn.example.com/nurofen.png"}'
                    '],"count":2}}'
                ).encode("utf-8")
            )

        repository = AptekaCartRepository(urlopen=fake_urlopen)
        snapshot = repository.get_cart(CartToken(access_token="tok-1", token_type="Bearer"))

        self.assertEqual(snapshot.items[0].image_url, None)
        self.assertEqual(snapshot.items[1].image_url, "https://cdn.example.com/nurofen.png")

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

    def test_apteka_repository_uses_apteka_base_url_from_env(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[str] = []

        def fake_urlopen(request, timeout: float):
            del timeout
            requests.append(request.full_url)
            return FakeResponse(b'{"accessToken":"token-123","tokenType":"Bearer"}')

        with patch.dict(os.environ, {"APTEKA_BASE_URL": "https://prod.apteka.md"}, clear=False):
            repository = AptekaCartRepository(urlopen=fake_urlopen)
            repository.create_cart()

        self.assertEqual(requests, ["https://prod.apteka.md/api/v1/front/cart"])

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

    def test_upstash_rest_store_retries_get_on_transient_network_error(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        calls = {"count": 0}

        def fake_urlopen(request, timeout: float):
            del timeout
            del request
            calls["count"] += 1
            if calls["count"] == 1:
                raise URLError("temporary dns issue")
            return FakeResponse(
                b'{"result":"{\\"access_token\\":\\"token-77\\",\\"token_type\\":\\"Bearer\\"}"}'
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
        self.assertEqual(restored.access_token, "token-77")
        self.assertEqual(calls["count"], 2)

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
