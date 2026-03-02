"""MCP checkout tools."""

from __future__ import annotations

import json
import re
from threading import Lock
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen as default_urlopen

from app.domain.cart.repository import CartApiRepository, CartTokenStore
from app.interfaces.mcp.tools.cart_tools import my_cart
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id

APTEKA_REGIONS_URL = "https://stage.apteka.md/api/v1/front//regions"
APTEKA_CITIES_WITHOUT_REGIONS_URL = "https://stage.apteka.md/api/v1/front//cities-without-regions"
APTEKA_PHARMACIES_URL = "https://stage.apteka.md/api/v1/front//pharmacies/new-list"
APTEKA_PICKUP_CALCULATE_URL = "https://stage.apteka.md/api/v1/front/delivery/calculate/pick-up"
_CHECKOUT_REFERENCE_CACHE_LOCK = Lock()
_CHECKOUT_REFERENCE_CACHE: dict[str, list[dict[str, Any]]] | None = None
_SIMPLE_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SIMPLE_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class CheckoutReferenceRepository(Protocol):
    def get_regions(self) -> list[dict[str, Any]]: ...

    def get_cities_without_regions(self) -> list[dict[str, Any]]: ...

    def get_pharmacies(self) -> list[dict[str, Any]]: ...

    def get_pickup_timeslot(self, pharmacy_id: int) -> dict[str, Any]: ...


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

    def get_pickup_timeslot(self, pharmacy_id: int) -> dict[str, Any]:
        request = Request(url=f"{APTEKA_PICKUP_CALCULATE_URL}/{pharmacy_id}", method="GET")
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _load_collection(self, url: str) -> list[dict[str, Any]]:
        request = Request(url=url, method="GET")
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return _extract_collection(payload)


def checkout_order(
    *,
    cart_session_id: str | None = None,
    delivery_method: str | None = None,
    pickup_region_id: int | str | None = None,
    pickup_city_id: int | str | None = None,
    pickup_pharmacy_id: int | str | None = None,
    pickup_contact: dict[str, object] | None = None,
    comment: str | None = None,
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

    effective_reference_repository = reference_repository or AptekaCheckoutReferenceRepository()
    reference_data = _load_cached_checkout_reference_data(effective_reference_repository)

    if not delivery_method:
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

    if delivery_method == "courier_delivery":
        return {
            "status": "courier_delivery_not_implemented",
            "cart_session_id": resolved_session_id,
            "message": "Курьерскую доставку добавим следующим этапом.",
        }

    if delivery_method != "pickup":
        return {
            "status": "validation_error",
            "errors": [{"field": "delivery_method", "message": "Unsupported delivery method"}],
            "cart_session_id": resolved_session_id,
        }

    available_regions = _available_regions_with_pharmacies(reference_data)
    if pickup_region_id is None:
        return {
            "status": "pickup_contact_and_region",
            "cart_session_id": resolved_session_id,
            "available_regions": available_regions,
            "required_fields": {
                "first_name": "required|min:3",
                "last_name": "optional|min:3",
                "phone": "required|libphonenumber-compatible",
                "email": "optional|email-validator-compatible",
            },
        }

    normalized_region_id = _parse_positive_int(pickup_region_id)
    if normalized_region_id is None or not _contains_id(available_regions, normalized_region_id):
        return {
            "status": "validation_error",
            "errors": [{"field": "pickup_region_id", "message": "Invalid region selection"}],
            "cart_session_id": resolved_session_id,
        }

    available_cities = _available_cities_for_region(reference_data, normalized_region_id)
    if pickup_city_id is None:
        return {
            "status": "pickup_city_selection",
            "cart_session_id": resolved_session_id,
            "pickup_region_id": normalized_region_id,
            "available_cities": available_cities,
        }

    normalized_city_id = _parse_positive_int(pickup_city_id)
    if normalized_city_id is None or not _contains_id(available_cities, normalized_city_id):
        return {
            "status": "validation_error",
            "errors": [{"field": "pickup_city_id", "message": "Invalid city selection"}],
            "cart_session_id": resolved_session_id,
        }

    available_pharmacies = _available_pharmacies(reference_data, normalized_region_id, normalized_city_id)
    if pickup_pharmacy_id is None:
        return {
            "status": "pickup_pharmacy_selection",
            "cart_session_id": resolved_session_id,
            "pickup_region_id": normalized_region_id,
            "pickup_city_id": normalized_city_id,
            "available_pharmacies": available_pharmacies,
        }

    normalized_pharmacy_id = _parse_positive_int(pickup_pharmacy_id)
    selected_pharmacy = _find_pharmacy(available_pharmacies, normalized_pharmacy_id)
    if normalized_pharmacy_id is None or selected_pharmacy is None:
        return {
            "status": "validation_error",
            "errors": [{"field": "pickup_pharmacy_id", "message": "Invalid pharmacy selection"}],
            "cart_session_id": resolved_session_id,
        }

    pickup_window = effective_reference_repository.get_pickup_timeslot(normalized_pharmacy_id)

    if not pickup_contact:
        return {
            "status": "pickup_contact",
            "cart_session_id": resolved_session_id,
            "pickup": {
                "region_id": normalized_region_id,
                "city_id": normalized_city_id,
                "pharmacy_id": normalized_pharmacy_id,
                "pharmacy": selected_pharmacy,
                "pickup_window": pickup_window,
            },
            "required_fields": {
                "first_name": "required|min:3",
                "last_name": "optional|min:3",
                "phone": "required|libphonenumber-compatible",
                "email": "optional|email-validator-compatible",
            },
        }

    if comment is not None and not isinstance(comment, str):
        return {
            "status": "validation_error",
            "errors": [{"field": "comment", "message": "Comment must be text"}],
            "cart_session_id": resolved_session_id,
        }

    errors = _validate_pickup_contact(pickup_contact)
    if errors:
        return {
            "status": "validation_error",
            "errors": errors,
            "cart_session_id": resolved_session_id,
        }

    return {
        "status": "pickup_ready_for_submission",
        "cart_session_id": resolved_session_id,
        "submission_mode": "single_payload",
        "pickup": {
            "region_id": normalized_region_id,
            "city_id": normalized_city_id,
            "pharmacy_id": normalized_pharmacy_id,
            "pharmacy": selected_pharmacy,
            "pickup_window": pickup_window,
            "contact": {
                "first_name": str(pickup_contact.get("first_name", "")).strip(),
                "last_name": str(pickup_contact.get("last_name", "")).strip(),
                "phone": str(pickup_contact.get("phone", "")).strip(),
                "email": str(pickup_contact.get("email", "")).strip(),
            },
            "comment": comment or "",
        },
    }


def _parse_positive_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _contains_id(items: list[dict[str, Any]], item_id: int) -> bool:
    return any(_parse_positive_int(item.get("id")) == item_id for item in items)


def _available_regions_with_pharmacies(
    reference_data: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    region_ids_with_pharmacies: set[int] = set()
    for pharmacy in reference_data["pharmacies"]:
        region_node = pharmacy.get("region")
        if isinstance(region_node, dict):
            region_id = _parse_positive_int(region_node.get("id"))
        else:
            region_id = _parse_positive_int(pharmacy.get("region_id"))
        if region_id is not None:
            region_ids_with_pharmacies.add(region_id)

    return [
        _to_display_option(region)
        for region in reference_data["regions"]
        if _parse_positive_int(region.get("id")) in region_ids_with_pharmacies
    ]


def _available_cities_for_region(
    reference_data: dict[str, list[dict[str, Any]]],
    region_id: int,
) -> list[dict[str, Any]]:
    pharmacy_city_ids = {
        city_id
        for city_id in (
            _extract_pharmacy_city_id(pharmacy, region_id) for pharmacy in reference_data["pharmacies"]
        )
        if city_id is not None
    }
    return [
        _to_display_option(city)
        for city in reference_data["cities_without_regions"]
        if _parse_positive_int(city.get("region_id")) == region_id
        and _parse_positive_int(city.get("id")) in pharmacy_city_ids
    ]


def _to_display_option(node: dict[str, Any]) -> dict[str, Any]:
    item_id = _parse_positive_int(node.get("id"))
    if item_id is None:
        item_id = 0
    return {"id": item_id, "name": _extract_name(node)}


def _extract_name(node: dict[str, Any]) -> str:
    translations = node.get("translations")
    if isinstance(translations, dict):
        ru = translations.get("ru")
        if isinstance(ru, dict):
            ru_name = str(ru.get("name") or "").strip()
            if ru_name:
                return ru_name
        ro = translations.get("ro")
        if isinstance(ro, dict):
            ro_name = str(ro.get("name") or "").strip()
            if ro_name:
                return ro_name
    return str(node.get("name") or "").strip()


def _available_pharmacies(
    reference_data: dict[str, list[dict[str, Any]]],
    region_id: int,
    city_id: int,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for pharmacy in reference_data["pharmacies"]:
        normalized_region_id = None
        region_node = pharmacy.get("region")
        if isinstance(region_node, dict):
            normalized_region_id = _parse_positive_int(region_node.get("id"))
        if normalized_region_id is None:
            normalized_region_id = _parse_positive_int(pharmacy.get("region_id"))
        if normalized_region_id != region_id:
            continue

        normalized_city_id = _extract_pharmacy_city_id(pharmacy, region_id)
        if normalized_city_id != city_id:
            continue
        matched.append(pharmacy)
    return matched


def _find_pharmacy(
    pharmacies: list[dict[str, Any]],
    pharmacy_id: int | None,
) -> dict[str, Any] | None:
    if pharmacy_id is None:
        return None
    for pharmacy in pharmacies:
        if _parse_positive_int(pharmacy.get("id")) == pharmacy_id:
            return pharmacy
    return None


def _extract_pharmacy_city_id(pharmacy: dict[str, Any], region_id: int) -> int | None:
    city_node = pharmacy.get("city")
    if isinstance(city_node, dict):
        city_id = _parse_positive_int(city_node.get("id"))
        if city_id is not None:
            return city_id

    for key in ("city_id", "locality_id", "settlement_id"):
        city_id = _parse_positive_int(pharmacy.get(key))
        if city_id is not None:
            return city_id

    sector_node = pharmacy.get("sector")
    if isinstance(sector_node, dict):
        sector_region_id = _parse_positive_int(sector_node.get("region_id"))
        if sector_region_id == region_id:
            sector_id = _parse_positive_int(sector_node.get("id"))
            if sector_id is not None:
                return sector_id
    return None


def _validate_pickup_contact(contact: dict[str, object]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    first_name = str(contact.get("first_name") or "").strip()
    last_name = str(contact.get("last_name") or "").strip()
    phone = str(contact.get("phone") or "").strip()
    email = str(contact.get("email") or "").strip()

    if len(first_name) < 3:
        errors.append({"field": "first_name", "message": "First name must be at least 3 characters"})

    if last_name and len(last_name) < 3:
        errors.append({"field": "last_name", "message": "Last name must be at least 3 characters"})

    if not _is_valid_phone(phone):
        errors.append({"field": "phone", "message": "Phone number is invalid"})

    if email and not _is_valid_email(email):
        errors.append({"field": "email", "message": "Email is invalid"})
    return errors


def _is_valid_phone(phone: str) -> bool:
    try:
        import phonenumbers  # type: ignore

        parsed = phonenumbers.parse(phone, None)
        return bool(phonenumbers.is_valid_number(parsed))
    except Exception:  # noqa: BLE001
        return bool(_SIMPLE_PHONE_PATTERN.match(phone))


def _is_valid_email(email: str) -> bool:
    try:
        from email_validator import validate_email  # type: ignore

        validate_email(email)
        return True
    except Exception:  # noqa: BLE001
        return bool(_SIMPLE_EMAIL_PATTERN.match(email))


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
