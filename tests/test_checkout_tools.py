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
        self.confirm_payloads: list[dict[str, object]] = []

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
            {
                "id": 9004,
                "region": {"id": 2},
                "city_id": 201,
                "translations": {"ru": {"name": "Pharmacy 9004"}},
            },
            {
                "id": 9010,
                "region": {"id": 2},
                "city_id": 201,
                "sector": {
                    "id": 202,
                    "region_id": 999,
                    "translations": {"ru": {"name": "Hospital Sector"}},
                },
                "translations": {"ru": {"name": "Pharmacy 9010"}},
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

    def confirm_order_by_mobile(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append("confirm_order_by_mobile")
        self.confirm_payloads.append(payload)
        return {"order_id": 12345, "status": "accepted"}


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
        self.assertEqual(payload["available_regions"], ["Region One", "Region Two"])

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
            pickup_region_name="Region Two",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_city_selection")
        self.assertEqual(payload["available_cities"], ["City 201", "Hospital Sector"])

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
            pickup_region_name="Region Two",
            pickup_city_name="City 201",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_pharmacy_selection")
        pharmacy_ids = [pharmacy["id"] for pharmacy in payload["available_pharmacies"]]
        self.assertEqual(pharmacy_ids, [9002, 9004])

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
            pickup_region_name="Region One",
            pickup_city_name="City 101",
            pickup_pharmacy_id=9001,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9001)
        self.assertEqual(payload["pickup"]["region_name"], "Region One")
        self.assertEqual(payload["pickup"]["city_name"], "City 101")
        self.assertEqual(payload["pickup"]["pickup_window"]["deliveryDate"], "02.03.2026")
        self.assertEqual(payload["pickup_window"]["deliveryDate"], "02.03.2026")
        self.assertIn("pickup_timeslot:9001", reference_repository.calls)

    def test_checkout_order_auto_selects_single_city_and_single_pharmacy_after_region(self) -> None:
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
            pickup_region_name="Region One",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["city_name"], "City 101")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9001)
        self.assertEqual(payload["pickup_window"]["deliveryDate"], "02.03.2026")

    def test_checkout_order_auto_selects_single_pharmacy_after_city(self) -> None:
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
            pickup_region_name="Region Two",
            pickup_city_name="Hospital Sector",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9010)
        self.assertEqual(payload["pickup"]["city_name"], "Hospital Sector")

    def test_checkout_order_pickup_accepts_pharmacy_name_selection(self) -> None:
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
            pickup_region_name="Region One",
            pickup_city_name="City 101",
            pickup_pharmacy_name="Pharmacy 9001",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9001)
        self.assertEqual(payload["pickup_window"]["deliveryDate"], "02.03.2026")

    def test_checkout_order_pickup_accepts_direct_pharmacy_without_city_name(self) -> None:
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
            pickup_region_name="Region Two",
            pickup_pharmacy_id=9002,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9002)
        self.assertEqual(payload["pickup"]["city_name"], "City 201")

    def test_checkout_order_pickup_prefers_direct_pharmacy_when_city_name_is_wrong(self) -> None:
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
            pickup_region_name="Region Two",
            pickup_city_name="Unknown City",
            pickup_pharmacy_id=9002,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_contact")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9002)
        self.assertEqual(payload["pickup"]["city_name"], "City 201")

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
            pickup_region_name="Region One",
            pickup_city_name="City 101",
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

    def test_checkout_order_pickup_rejects_phone_with_non_whitelisted_country_code(self) -> None:
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
            pickup_region_name="Region One",
            pickup_city_name="City 101",
            pickup_pharmacy_id=9001,
            pickup_contact={
                "first_name": "Alice",
                "phone": "+15551234567",
            },
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "validation_error")
        fields = {error["field"] for error in payload["errors"]}
        self.assertIn("phone", fields)

    def test_checkout_order_pickup_accepts_phone_from_whitelisted_country_code(self) -> None:
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
            pickup_region_name="Region One",
            pickup_city_name="City 101",
            pickup_pharmacy_id=9001,
            pickup_contact={
                "first_name": "Alice",
                "phone": "+407123456789",
            },
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_confirmation_and_payment")

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
            pickup_region_name="Region Two",
            pickup_city_name="City 201",
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
            pickup_region_name="Region Two",
            pickup_city_name="City 201",
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

        self.assertEqual(payload["status"], "pickup_confirmation_and_payment")
        self.assertEqual(payload["pickup"]["region_name"], "Region Two")
        self.assertEqual(payload["pickup"]["city_name"], "City 201")
        self.assertEqual(payload["pickup"]["pharmacy_id"], 9002)
        self.assertEqual(payload["pickup"]["pharmacy"]["id"], 9002)
        self.assertEqual(payload["pickup"]["pickup_window"]["deliveryDate"], "02.03.2026")
        self.assertEqual(payload["payment"]["required"], True)
        self.assertEqual(payload["required_confirmations"]["terms_accepted"], True)
        payment_option_ids = [item["id"] for item in payload["payment"]["options"]]
        self.assertEqual(
            payment_option_ids,
            ["card_on_receipt", "cash_on_receipt", "bank_transfer"],
        )

    def test_checkout_order_pickup_requires_payment_and_terms_for_submission(self) -> None:
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
            pickup_region_name="Region Two",
            pickup_city_name="City 201",
            pickup_pharmacy_id=9002,
            pickup_contact={
                "first_name": "Alice",
                "last_name": "Smith",
                "phone": "+37369111222",
                "email": "alice@example.com",
            },
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
            terms_accepted=False,
        )

        self.assertEqual(payload["status"], "validation_error")
        fields = {error["field"] for error in payload["errors"]}
        self.assertSetEqual(fields, {"payment_method", "terms_accepted"})
        self.assertEqual(reference_repository.confirm_payloads, [])

    def test_checkout_order_courier_returns_all_regions_before_selection(self) -> None:
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
            delivery_method="courier_delivery",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "courier_contact_and_region")
        self.assertEqual(
            payload["available_regions"],
            ["Region One", "Region Two", "Region Without Pharmacies"],
        )

    def test_checkout_order_courier_region_returns_cities_by_region(self) -> None:
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
            delivery_method="courier_delivery",
            courier_address={"region_name": "Region One"},
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "courier_city_selection")
        self.assertEqual(payload["available_cities"], ["City 101", "City 102"])

    def test_checkout_order_courier_validates_required_address_fields(self) -> None:
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
            delivery_method="courier_delivery",
            pickup_contact={"first_name": "Alice", "phone": "+37369111222"},
            courier_address={
                "region_name": "Region One",
                "city_name": "City 101",
            },
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "validation_error")
        fields = {error["field"] for error in payload["errors"]}
        self.assertSetEqual(fields, {"street", "house_number"})

    def test_checkout_order_courier_accepts_valid_contact_and_address(self) -> None:
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
            delivery_method="courier_delivery",
            pickup_contact={
                "first_name": "Alice",
                "last_name": "Smith",
                "phone": "+37369111222",
                "email": "alice@example.com",
            },
            courier_address={
                "region_name": "Region Two",
                "city_name": "City 201",
                "street": "Stefan cel Mare",
                "house_number": "10A",
                "apartment": "12",
                "entrance": "2",
                "floor": "4",
                "intercom_code": "42",
            },
            comment="Leave at door",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "courier_ready_for_submission")
        self.assertEqual(payload["courier"]["region_name"], "Region Two")
        self.assertEqual(payload["courier"]["city_name"], "City 201")
        self.assertEqual(payload["courier"]["address"]["street"], "Stefan cel Mare")
        self.assertEqual(payload["courier"]["address"]["house_number"], "10A")
        self.assertEqual(payload["courier"]["contact"]["first_name"], "Alice")
        self.assertEqual(payload["courier"]["comment"], "Leave at door")

    def test_checkout_order_pickup_submits_confirm_payload(self) -> None:
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
        add_to_my_cart(
            product_id="17406",
            cart_session_id=str(session["cart_session_id"]),
            repository=cart_repository,
            token_store=token_store,
        )

        payload = checkout_order(
            cart_session_id=str(session["cart_session_id"]),
            delivery_method="pickup",
            pickup_region_name="Region Two",
            pickup_city_name="City 201",
            pickup_pharmacy_id=9002,
            pickup_contact={
                "first_name": "Alice",
                "last_name": "Smith",
                "phone": "+37369111222",
                "email": "alice@example.com",
            },
            payment_method="cash_on_receipt",
            dont_call_me=True,
            terms_accepted=True,
            comment="No call please",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "order_submitted")
        self.assertEqual(payload["confirm_response"]["order_id"], 12345)
        self.assertEqual(len(reference_repository.confirm_payloads), 1)
        submitted = reference_repository.confirm_payloads[0]
        self.assertEqual(submitted["orderType"], "mobile")
        self.assertEqual(submitted["dontCallMe"], True)
        self.assertEqual(submitted["payment"]["type"], "cash_on_receipt")
        self.assertEqual(submitted["delivery"]["type"], "PICK_UP")
        self.assertEqual(submitted["delivery"]["pharmacy_id"], 9002)

    def test_pickup_timeslot_request_uses_selected_pharmacy_item_id(self) -> None:
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
            delivery_method="pickup",
            pickup_region_name="Region Two",
            pickup_city_name="City 201",
            pickup_pharmacy_id=9002,
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertIn("pickup_timeslot:9002", reference_repository.calls)
        self.assertNotIn("pickup_timeslot:2", reference_repository.calls)
        self.assertNotIn("pickup_timeslot:201", reference_repository.calls)

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

    def test_checkout_reference_repository_calls_confirm_endpoint(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[tuple[str, str, bytes]] = []

        def fake_urlopen(request, timeout: float):
            del timeout
            requests.append((request.full_url, request.get_method(), request.data))
            return FakeResponse(b'{"ok":true}')

        repository = AptekaCheckoutReferenceRepository(urlopen=fake_urlopen)
        response = repository.confirm_order_by_mobile({"dontCallMe": False})

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["body"], {"ok": True})
        self.assertEqual(response["raw_body"], None)
        self.assertEqual(len(requests), 1)
        self.assertEqual(
            requests[0][0],
            "https://stage.apteka.md/api/v1/front/order/confirm-order-by-using-mobile",
        )
        self.assertEqual(requests[0][1], "POST")
        self.assertEqual(requests[0][2], b'{"dontCallMe":false}')

    def test_checkout_reference_repository_confirm_handles_empty_response_body(self) -> None:
        class FakeResponse:
            status = 200

            def read(self) -> bytes:
                return b""

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        def fake_urlopen(request, timeout: float):
            del request, timeout
            return FakeResponse()

        repository = AptekaCheckoutReferenceRepository(urlopen=fake_urlopen)
        response = repository.confirm_order_by_mobile({"dontCallMe": False})

        self.assertEqual(response["status_code"], 200)
        self.assertEqual(response["ok"], True)
        self.assertEqual(response["body"], None)

    def test_city_selection_prefers_sector_id_over_city_id_when_present(self) -> None:
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
            pickup_region_name="Region Two",
            repository=cart_repository,
            token_store=token_store,
            reference_repository=reference_repository,
        )

        self.assertEqual(payload["status"], "pickup_city_selection")
        self.assertEqual(payload["available_cities"], ["City 201", "Hospital Sector"])


if __name__ == "__main__":
    unittest.main()
