"""Checkout validators."""

from __future__ import annotations

import re
from typing import Callable

from app.domain.checkout.entities import CheckoutContact, CourierAddress

_SIMPLE_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SIMPLE_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


PhoneValidator = Callable[[str], bool]
EmailValidator = Callable[[str], bool]


def _default_phone_validator(phone: str) -> bool:
    return bool(_SIMPLE_PHONE_PATTERN.match(phone))


def _default_email_validator(email: str) -> bool:
    return bool(_SIMPLE_EMAIL_PATTERN.match(email))


def validate_pickup_contact(
    contact: CheckoutContact,
    *,
    phone_validator: PhoneValidator | None = None,
    email_validator: EmailValidator | None = None,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if len(contact.first_name) < 3:
        errors.append({"field": "first_name", "message": "First name must be at least 3 characters"})

    if contact.last_name and len(contact.last_name) < 3:
        errors.append({"field": "last_name", "message": "Last name must be at least 3 characters"})

    active_phone_validator = phone_validator or _default_phone_validator
    if not active_phone_validator(contact.phone):
        errors.append({"field": "phone", "message": "Phone number is invalid"})

    active_email_validator = email_validator or _default_email_validator
    if contact.email and not active_email_validator(contact.email):
        errors.append({"field": "email", "message": "Email is invalid"})
    return errors


def validate_courier_address(address: CourierAddress) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if not address.street:
        errors.append({"field": "street", "message": "Street is required"})
    if not address.house_number:
        errors.append({"field": "house_number", "message": "House number is required"})
    return errors


def validate_confirmation_fields(
    *,
    payment_method: str | None,
    terms_accepted: bool | None,
    payment_method_ids: set[str],
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    normalized_payment_method = str(payment_method or "").strip()
    if not normalized_payment_method:
        errors.append({"field": "payment_method", "message": "Payment method is required"})
    elif normalized_payment_method not in payment_method_ids:
        errors.append({"field": "payment_method", "message": "Unsupported payment method"})

    if terms_accepted is not True:
        errors.append({"field": "terms_accepted", "message": "Terms agreement is required"})
    return errors
