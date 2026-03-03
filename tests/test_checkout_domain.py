"""Tests for checkout domain entities, validators, and service."""

from __future__ import annotations

import unittest

from app.domain.checkout.entities import CheckoutContact, CourierAddress
from app.domain.checkout.service import CheckoutValidationService


class CheckoutDomainTests(unittest.TestCase):
    def test_checkout_contact_from_payload_normalizes_values(self) -> None:
        contact = CheckoutContact.from_payload(
            {
                "first_name": "  Alice ",
                "last_name": "  Smith ",
                "phone": " +37369111222 ",
                "email": " alice@example.com ",
            }
        )

        self.assertEqual(contact.first_name, "Alice")
        self.assertEqual(contact.last_name, "Smith")
        self.assertEqual(contact.phone, "+37369111222")
        self.assertEqual(contact.email, "alice@example.com")

    def test_courier_address_from_payload_normalizes_values(self) -> None:
        address = CourierAddress.from_payload(
            {
                "street": " Stefan cel Mare ",
                "house_number": " 10A ",
                "apartment": " 12 ",
                "entrance": " 2 ",
                "floor": " 4 ",
                "intercom_code": " 42 ",
            }
        )

        self.assertEqual(address.street, "Stefan cel Mare")
        self.assertEqual(address.house_number, "10A")
        self.assertEqual(address.apartment, "12")
        self.assertEqual(address.entrance, "2")
        self.assertEqual(address.floor, "4")
        self.assertEqual(address.intercom_code, "42")

    def test_validation_service_checks_pickup_contact(self) -> None:
        service = CheckoutValidationService()
        errors = service.validate_pickup_contact(
            CheckoutContact.from_payload(
                {
                    "first_name": "Al",
                    "last_name": "Iv",
                    "phone": "12345",
                    "email": "broken-email",
                }
            )
        )

        fields = {error["field"] for error in errors}
        self.assertSetEqual(fields, {"first_name", "last_name", "phone", "email"})

    def test_validation_service_checks_courier_address(self) -> None:
        service = CheckoutValidationService()
        errors = service.validate_courier_address(
            CourierAddress.from_payload({"street": " ", "house_number": " "})
        )

        fields = {error["field"] for error in errors}
        self.assertSetEqual(fields, {"street", "house_number"})


if __name__ == "__main__":
    unittest.main()
