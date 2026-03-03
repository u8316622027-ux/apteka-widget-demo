"""Checkout business rules."""

from __future__ import annotations

from dataclasses import asdict

from app.domain.checkout.entities import CheckoutContact, CourierAddress
from app.domain.checkout.validators import (
    EmailValidator,
    PhoneValidator,
    validate_confirmation_fields,
    validate_courier_address,
    validate_pickup_contact,
)


class CheckoutValidationService:
    """Domain-level checkout validators orchestrator."""

    def __init__(
        self,
        *,
        phone_validator: PhoneValidator | None = None,
        email_validator: EmailValidator | None = None,
        payment_method_ids: set[str] | None = None,
    ) -> None:
        self._phone_validator = phone_validator
        self._email_validator = email_validator
        self._payment_method_ids = payment_method_ids or set()

    def validate_pickup_contact(self, contact: CheckoutContact) -> list[dict[str, str]]:
        return validate_pickup_contact(
            contact,
            phone_validator=self._phone_validator,
            email_validator=self._email_validator,
        )

    def validate_courier_address(
        self, address: CourierAddress | dict[str, object]
    ) -> list[dict[str, str]]:
        if isinstance(address, CourierAddress):
            normalized = address
        else:
            normalized = CourierAddress.from_payload(address)
        return validate_courier_address(normalized)

    def validate_confirmation_fields(
        self,
        *,
        payment_method: str | None,
        terms_accepted: bool | None,
    ) -> list[dict[str, str]]:
        return validate_confirmation_fields(
            payment_method=payment_method,
            terms_accepted=terms_accepted,
            payment_method_ids=self._payment_method_ids,
        )

    def normalize_courier_address(self, address_payload: dict[str, object]) -> dict[str, str]:
        return asdict(CourierAddress.from_payload(address_payload))
