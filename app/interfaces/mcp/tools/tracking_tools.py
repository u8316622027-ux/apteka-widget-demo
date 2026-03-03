"""MCP tracking tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen as default_urlopen

from app.core.env import read_env_file_value
from app.domain.tracking.repository import OrderTrackingRepository
from app.domain.tracking.service import OrderTrackingService
from app.interfaces.mcp.tools.apteka_urls import build_api_url

APTEKA_ORDER_TRACKING_PATH = "/api/orders-by-anything"
APTEKA_TRACKING_AUTHORIZATION_ENV = "APTEKA_TRACKING_AUTHORIZATION"
ENV_FILE_PATH = Path(__file__).resolve().parents[4] / ".env"
ORDER_STATUS_LABELS = {
    "pending": "заказ получен",
    "processing": "заказ обрабатывается",
    "packaging": "заказ собирается",
    "packed": "заказ собран",
    "delivering": "заказ в пути",
    "client_notified": "заказ готов, клиент уведомлен",
    "canceled": "заказ отменен",
    "completed": "заказ выполнен",
    "draft": "черновик",
    "new": "только создан, ожидание обработки",
}
ORDER_STATUS_HINTS = {
    "pending": (
        "Заказ только получен и еще не подтвержден оператором. "
        "Нужно дождаться обработки."
    ),
    "processing": "Заказ уже в работе у аптеки, но пока не готов к выдаче или доставке.",
    "packaging": "Заказ собирается. Пока рано ехать за ним или ждать курьера.",
    "packed": (
        "Заказ собран, но еще не готов к выдаче. "
        "Это не означает, что его уже можно забрать. "
        "Ориентируйтесь на статус 'client_notified' как сигнал готовности."
    ),
    "delivering": "Заказ передан в доставку и находится в пути к клиенту.",
    "client_notified": "Заказ готов к выдаче/получению, клиент уже уведомлен.",
    "canceled": "Заказ отменен и не будет доставлен или выдан.",
    "completed": "Заказ выполнен и закрыт.",
    "draft": "Черновик заказа, оформление еще не завершено.",
    "new": (
        "Заказ только создан. При поиске по номеру заказа может понадобиться подождать, "
        "пока оператор примет заказ."
    ),
}
DEFAULT_STATUS_HINT = "Проверьте детали заказа или свяжитесь с поддержкой для уточнения статуса."


class AptekaOrderTrackingRepository(OrderTrackingRepository):
    """HTTP-backed repository for stage order tracking endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 10.0,
        authorization: str | None = None,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = (base_url or build_api_url(APTEKA_ORDER_TRACKING_PATH)).rstrip("/")
        self._timeout = timeout
        self._authorization = authorization or _resolve_authorization()
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
    mapped_orders = [_map_order_status(order) for order in orders]
    return {"lookup": normalized_lookup, "count": len(mapped_orders), "orders": mapped_orders}


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


def _map_order_status(order: dict[str, Any]) -> dict[str, Any]:
    raw_status = order.get("status")
    if not isinstance(raw_status, str):
        return dict(order)

    normalized_status = raw_status.strip()
    if not normalized_status:
        return dict(order)

    normalized_key = normalized_status.lower()
    status_label = ORDER_STATUS_LABELS.get(normalized_key, normalized_status)
    status_hint = ORDER_STATUS_HINTS.get(normalized_key, DEFAULT_STATUS_HINT)
    mapped_order = dict(order)
    mapped_order["status_code"] = normalized_status
    mapped_order["status"] = status_label
    mapped_order["status_hint"] = status_hint
    return mapped_order


def _resolve_authorization() -> str:
    env_value = os.getenv(APTEKA_TRACKING_AUTHORIZATION_ENV, "").strip()
    if env_value:
        return env_value
    return read_env_file_value(APTEKA_TRACKING_AUTHORIZATION_ENV, env_path=ENV_FILE_PATH)
