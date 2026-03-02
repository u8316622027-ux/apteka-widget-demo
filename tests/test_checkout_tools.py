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
        return [
            {"id": 1, "translations": {"ru": {"name": "Region One"}}},
            {"id": 2, "translations": {"ru": {"name": "Region Two"}}},
            {"id": 3, "translations": {"ru": {"name": "Region Without Pharmacies"}}},
        ]

    def get_cities_without_regions(self) -> list[dict[str, object]]:
        self.calls.append("cities_without_regions")
        return [
            {"id": 101, "region_id": 1, "translations": {"ru": {"name": "City 101"}}},
            {"id": 102, "region_id": 1, "translations": {"ru": {"name": "City 102"}}},
            {"id": 201, "region_id": 2, "translations": {"ru": {"name": "City 201"}}},
        ]

    def get_pharmacies(self) -> list[dict[str, object]]:
        self.calls.append("pharmacies")
        return [
            {
                "id": 9001,
                "region": {"id": 1},
                "city": {"id": 101},
                "translations": {"ru": {"name": "Pharmacy 9001"}},
            },
            {
                "id": 9002,
                "region": {"id": 2},
                "city_id": 201,
                "translations": {"ru": {"name": "Pharmacy 9002"}},
            },
        ]

    def get_pickup_timeslot(self, pharmacy_id: int) -> dict[str, object]:
        self.calls.append(f"pickup_timeslot:{pharmacy_id}")
        return {
            "deliveryDate": "02.03.2026",
            "from": "14:00",
            "to": "20:00",
            "orderEnd": "05.03.2026",
            "pharmacyClose": "20:00",
        }


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

    def test_checkout_order_pickup_returns_only_regions_with_pharmacies(self) -> None:
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
            delivery_method="pickup",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact_and_region")
        region_ids = [region["id"] for region in payload["available_regions"]]
        self.assertEqual(region_ids, [1, 2])
        self.assertTrue(
            all(set(region.keys()) == {"id", "name"} for region in payload["available_regions"])
        )

    def test_checkout_order_pickup_region_returns_cities_with_pharmacies(self) -> None:
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
            delivery_method="pickup",
            pickup_region_id=1,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_city_selection")
        city_ids = [city["id"] for city in payload["available_cities"]]
        self.assertEqual(city_ids, [101])
        self.assertTrue(all(set(city.keys()) == {"id", "name"} for city in payload["available_cities"]))

    def test_checkout_order_pickup_city_returns_pharmacies(self) -> None:
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
            delivery_method="pickup",
            pickup_region_id=1,
            pickup_city_id=101,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_pharmacy_selection")
        pharmacy_ids = [pharmacy["id"] for pharmacy in payload["available_pharmacies"]]
        self.assertEqual(pharmacy_ids, [9001])

    def test_checkout_order_pickup_pharmacy_returns_pickup_window(self) -> None:
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
            delivery_method="pickup",
            pickup_region_id=1,
            pickup_city_id=101,
            pickup_pharmacy_id=9001,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9001)
        self.assertEqual(payload["pickup"]["pickup_window"]["deliveryDate"], "02.03.2026")
        self.assertIn("pickup_timeslot:9001", reference_repository.calls)

    def test_checkout_order_pickup_validates_contact_fields(self) -> None:
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
            delivery_method="pickup",
            pickup_region_id=1,
            pickup_city_id=101,
            pickup_pharmacy_id=9001,
            pickup_contact={
                "first_name": "Al",
                "last_name": "Iv",
                "phone": "12345",
                "email": "broken-email",
            },
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "validation_error")
        fields = {error["field"] for error in payload["errors"]}
        self.assertSetEqual(fields, {"first_name", "last_name", "phone", "email"})

    def test_checkout_order_pickup_rejects_skipping_pharmacy_selection(self) -> None:
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
            delivery_method="pickup",
            pickup_region_id=1,
            pickup_city_id=101,
            pickup_contact={"first_name": "Alice", "phone": "+37369111222"},
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_pharmacy_selection")

    def test_checkout_order_pickup_accepts_valid_contact_payload(self) -> None:
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
            delivery_method="pickup",
            pickup_region_id=2,
            pickup_city_id=201,
            pickup_pharmacy_id=9002,
            pickup_contact={
                "first_name": "Alice",
                "last_name": "Smith",
                "phone": "+37369111222",
                "email": "alice@example.com",
            },
            comment="Call before delivery",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_ready_for_submission")
        self.assertEqual(payload["pickup"]["region_id"], 2)
        self.assertEqual(payload["pickup"]["city_id"], 201)
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9002)
        self.assertEqual(payload["pickup"]["pharmacy"]["id"], 9002)
        self.assertEqual(payload["pickup"]["pickup_window"]["deliveryDate"], "02.03.2026")

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
        repository.get_pickup_timeslot(9001)

        self.assertEqual(
            requests,
            [
                ("https://stage.apteka.md/api/v1/front//regions", "GET"),
                ("https://stage.apteka.md/api/v1/front//cities-without-regions", "GET"),
                ("https://stage.apteka.md/api/v1/front//pharmacies/new-list", "GET"),
                ("https://stage.apteka.md/api/v1/front/delivery/calculate/pick-up/9001", "GET"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
