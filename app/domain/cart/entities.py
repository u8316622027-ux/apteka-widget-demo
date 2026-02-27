"""Cart entities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CartToken:
    """Access token pair used for cart API authorization."""

    access_token: str
    token_type: str


@dataclass(frozen=True, slots=True)
class CartItem:
    """Single cart line item."""

    product_id: str
    quantity: int


@dataclass(frozen=True, slots=True)
class CartSnapshot:
    """Current cart state as returned by API."""

    items: list[CartItem]
    count: int
    total: float | None
