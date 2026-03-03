"""Checkout entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


def _clean(payload: Mapping[str, object], key: str) -> str:
    return str(payload.get(key) or "").strip()


@dataclass(frozen=True, slots=True)
class CheckoutContact:
    first_name: str
    last_name: str
    phone: str
    email: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "CheckoutContact":
        return cls(
            first_name=_clean(payload, "first_name"),
            last_name=_clean(payload, "last_name"),
            phone=_clean(payload, "phone"),
            email=_clean(payload, "email"),
        )


@dataclass(frozen=True, slots=True)
class CourierAddress:
    street: str
    house_number: str
    apartment: str
    entrance: str
    floor: str
    intercom_code: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "CourierAddress":
        return cls(
            street=_clean(payload, "street"),
            house_number=_clean(payload, "house_number"),
            apartment=_clean(payload, "apartment"),
            entrance=_clean(payload, "entrance"),
            floor=_clean(payload, "floor"),
            intercom_code=_clean(payload, "intercom_code"),
        )
