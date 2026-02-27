"""Product entities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductSummary:
    """Simplified product model used by search flows."""

    product_id: str
    name: str
    price: float | None
    image_url: str | None
    product_url: str | None
