"""MCP checkout tools."""

from __future__ import annotations

import json
from threading import Lock
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen as default_urlopen

from app.domain.cart.repository import CartApiRepository, CartTokenStore
from app.interfaces.mcp.tools.cart_tools import my_cart
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id

APTEKA_REGIONS_URL = "https://stage.apteka.md/api/v1/front//regions"
APTEKA_CITIES_WITHOUT_REGIONS_URL = "https://stage.apteka.md/api/v1/front//cities-without-regions"
APTEKA_PHARMACIES_URL = "https://stage.apteka.md/api/v1/front//pharmacies/new-list"
_CHECKOUT_REFERENCE_CACHE_LOCK = Lock()
_CHECKOUT_REFERENCE_CACHE: dict[str, list[dict[str, Any]]] | None = None


class CheckoutReferenceRepository(Protocol):
    def get_regions(self) -> list[dict[str, Any]]: ...

    def get_cities_without_regions(self) -> list[dict[str, Any]]: ...

    def get_pharmacies(self) -> list[dict[str, Any]]: ...


class AptekaCheckoutReferenceRepository:
    """Loads checkout reference lists from stage endpoints."""

    def __init__(
        self,
        *,
        regions_url: str = APTEKA_REGIONS_URL,
        cities_without_regions_url: str = APTEKA_CITIES_WITHOUT_REGIONS_URL,
        pharmacies_url: str = APTEKA_PHARMACIES_URL,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._regions_url = regions_url
        self._cities_without_regions_url = cities_without_regions_url
        self._pharmacies_url = pharmacies_url
        self._timeout = timeout
        self._urlopen = urlopen

    def get_regions(self) -> list[dict[str, Any]]:
        return self._load_collection(self._regions_url)

    def get_cities_without_regions(self) -> list[dict[str, Any]]:
        return self._load_collection(self._cities_without_regions_url)

    def get_pharmacies(self) -> list[dict[str, Any]]:
        return self._load_collection(self._pharmacies_url)

    def _load_collection(self, url: str) -> list[dict[str, Any]]:
        request = Request(url=url, method="GET")
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _extract_collection(payload)


def checkout_order(
    *,
    cart_session_id: str | None = None,
    repository: CartApiRepository | None = None,
    token_store: CartTokenStore | None = None,
    reference_repository: CheckoutReferenceRepository | None = None,
) -> dict[str, object]:
    """Tool entrypoint for checkout step orchestration."""

    normalized_session_id = normalize_cart_session_id(cart_session_id)
    cart_payload = my_cart(
        cart_session_id=normalized_session_id,
        repository=repository,
        token_store=token_store,
    )
    cart_count = int(cart_payload.get("count") or 0)
    resolved_session_id = str(cart_payload.get("cart_session_id") or "")
    if cart_count <= 0:
        return {
            "status": "cart_empty",
            "cart_session_id": resolved_session_id,
            "message": (
                "Пока в корзине нет товаров. Добавьте хотя бы один товар, "
                "и я помогу сразу перейти к оформлению заказа."
            ),
        }

    reference_data = _load_cached_checkout_reference_data(
        reference_repository or AptekaCheckoutReferenceRepository()
    )
    return {
        "status": "delivery_method_selection",
        "cart_session_id": resolved_session_id,
        "cart_count": cart_count,
        "cart_total": cart_payload.get("total"),
        "delivery_options": [
            {
                "id": "pickup",
                "title": "Самовывоз",
                "description": "Бесплатная доставка в аптеки по всей стране.",
            },
            {
                "id": "courier_delivery",
                "title": "Курьерская доставка",
                "description": "Доставка по Молдове осуществляется нашей курьерской службой.",
            },
        ],
        "reference_data_meta": {
            "regions_count": len(reference_data["regions"]),
            "cities_without_regions_count": len(reference_data["cities_without_regions"]),
            "pharmacies_count": len(reference_data["pharmacies"]),
        },
    }


def _load_cached_checkout_reference_data(
    repository: CheckoutReferenceRepository,
) -> dict[str, list[dict[str, Any]]]:
    global _CHECKOUT_REFERENCE_CACHE
    with _CHECKOUT_REFERENCE_CACHE_LOCK:
        if _CHECKOUT_REFERENCE_CACHE is None:
            _CHECKOUT_REFERENCE_CACHE = {
                "regions": repository.get_regions(),
                "cities_without_regions": repository.get_cities_without_regions(),
                "pharmacies": repository.get_pharmacies(),
            }
        return _CHECKOUT_REFERENCE_CACHE


def _clear_checkout_reference_cache() -> None:
    global _CHECKOUT_REFERENCE_CACHE
    with _CHECKOUT_REFERENCE_CACHE_LOCK:
        _CHECKOUT_REFERENCE_CACHE = None


def _extract_collection(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []
