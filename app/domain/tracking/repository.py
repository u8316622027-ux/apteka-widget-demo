"""Tracking repository contracts."""

from __future__ import annotations

from typing import Any, Protocol


class OrderTrackingRepository(Protocol):
    """Repository contract for order tracking lookups."""

    def lookup(self, lookup_value: str) -> list[dict[str, Any]]:
        """Return matching orders for provided phone or order number."""
