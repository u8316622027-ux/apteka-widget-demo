"""MCP tracking tools."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen as default_urlopen

from app.domain.tracking.repository import OrderTrackingRepository
from app.domain.tracking.service import OrderTrackingService

APTEKA_ORDER_TRACKING_URL = "https://stage.apteka.md/api/orders-by-anything"
APTEKA_TRACKING_AUTHORIZATION_ENV = "APTEKA_TRACKING_AUTHORIZATION"


class AptekaOrderTrackingRepository(OrderTrackingRepository):
    """HTTP-backed repository for stage order tracking endpoint."""

    def __init__(
        self,
        *,
        base_url: str = APTEKA_ORDER_TRACKING_URL,
        timeout: float = 10.0,
        authorization: str | None = None,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._authorization = authorization or os.getenv(APTEKA_TRACKING_AUTHORIZATION_ENV, "")
        self._urlopen = urlopen

    def lookup(self, lookup_value: str) -> list[dict[str, Any]]:
        encoded_value = quote(lookup_value, safe="")
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._authorization.strip():
            headers["Authorization"] = self._authorization.strip()

        request = Request(url=f"{self._base_url}/{encoded_value}", method="GET", headers=headers)
        with self._urlopen(request, timeout=self._timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        return _extract_orders(response_payload)


def track_order_status_ui(
    lookup: str,
    *,
    repository: OrderTrackingRepository | None = None,
) -> dict[str, Any]:
    """Tool entrypoint for order status tracking."""

    effective_repository = repository or AptekaOrderTrackingRepository()
    service = OrderTrackingService(effective_repository)
    normalized_lookup, orders = service.track(lookup)
    return {"lookup": normalized_lookup, "count": len(orders), "orders": orders}


def _extract_orders(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("orders", "data", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    if any(key in payload for key in ("status", "order_number", "orderNumber", "id")):
        return [payload]

    return []
