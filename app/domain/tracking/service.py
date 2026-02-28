"""Tracking business rules."""

from __future__ import annotations

from typing import Any

from app.domain.tracking.repository import OrderTrackingRepository


class OrderTrackingService:
    """Use-case level service for order status tracking."""

    def __init__(self, repository: OrderTrackingRepository) -> None:
        self._repository = repository

    def track(self, lookup_value: str) -> tuple[str, list[dict[str, Any]]]:
        normalized_lookup = lookup_value.strip()
        if not normalized_lookup:
            raise ValueError("lookup must not be empty")
        return normalized_lookup, self._repository.lookup(normalized_lookup)
