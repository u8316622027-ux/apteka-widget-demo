"""MCP checkout tools."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from time import monotonic as _monotonic
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen as default_urlopen

from app.core.config import get_settings
from app.domain.cart.repository import CartApiRepository, CartTokenStore
from app.domain.checkout.entities import CheckoutContact
from app.domain.checkout.service import CheckoutValidationService
from app.interfaces.mcp.tools.apteka_urls import build_front_url
from app.interfaces.mcp.tools.cart_tools import my_cart
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id

APTEKA_REGIONS_PATH = "//regions"
APTEKA_CITIES_WITHOUT_REGIONS_PATH = "//cities-without-regions"
APTEKA_PHARMACIES_PATH = "//pharmacies/new-list"
APTEKA_PICKUP_CALCULATE_PATH = "/delivery/calculate/pick-up"
APTEKA_CONFIRM_ORDER_PATH = "/order/confirm-order-by-using-mobile"
CHECKOUT_REFERENCE_CACHE_TTL_SECONDS = 300.0
_ALLOWED_PHONE_RULES_LOCK = Lock()
_ALLOWED_PHONE_RULES_CACHE: list[dict[str, Any]] | None = None
_SIMPLE_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SIMPLE_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")
_NON_DIGITS_PATTERN = re.compile(r"\D+")
_PAYMENT_METHOD_OPTIONS = [
    {
        "id": "card_on_receipt",
        "title": "Картой при получении",
    },
    {
        "id": "cash_on_receipt",
        "title": "Наличными при получении",
    },
    {
        "id": "bank_transfer",
        "title": "Перечислением",
    },
]
_PAYMENT_METHOD_IDS = {option["id"] for option in _PAYMENT_METHOD_OPTIONS}
_ALLOWED_PHONE_CODES_PATH = Path(__file__).resolve().parents[3] / "data" / "allowed_phone_codes.json"


@dataclass(slots=True)
class _CheckoutReferenceCacheState:
    lock: Lock
    payload: tuple[float, dict[str, list[dict[str, Any]]]] | None = None


class CheckoutReferenceRepository(Protocol):
    def get_regions(self) -> list[dict[str, Any]]: ...

    def get_cities_without_regions(self) -> list[dict[str, Any]]: ...

    def get_pharmacies(self) -> list[dict[str, Any]]: ...

    def get_pickup_timeslot(self, pharmacy_id: int) -> dict[str, Any]: ...

    def confirm_order_by_mobile(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class AptekaCheckoutReferenceRepository:
    """Loads checkout reference lists from stage endpoints."""

    def __init__(
        self,
        *,
        regions_url: str | None = None,
        cities_without_regions_url: str | None = None,
        pharmacies_url: str | None = None,
        pickup_calculate_url: str | None = None,
        confirm_order_url: str | None = None,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._regions_url = regions_url or build_front_url(APTEKA_REGIONS_PATH)
        self._cities_without_regions_url = cities_without_regions_url or build_front_url(
            APTEKA_CITIES_WITHOUT_REGIONS_PATH
        )
        self._pharmacies_url = pharmacies_url or build_front_url(APTEKA_PHARMACIES_PATH)
        self._pickup_calculate_url = pickup_calculate_url or build_front_url(APTEKA_PICKUP_CALCULATE_PATH)
        self._confirm_order_url = confirm_order_url or build_front_url(APTEKA_CONFIRM_ORDER_PATH)
        self._timeout = timeout
        self._urlopen = urlopen

    def get_regions(self) -> list[dict[str, Any]]:
        return self._load_collection(self._regions_url)

    def get_cities_without_regions(self) -> list[dict[str, Any]]:
        return self._load_collection(self._cities_without_regions_url)

    def get_pharmacies(self) -> list[dict[str, Any]]:
        return self._load_collection(self._pharmacies_url)

    def get_pickup_timeslot(self, pharmacy_id: int) -> dict[str, Any]:
        request = Request(url=f"{self._pickup_calculate_url}/{pharmacy_id}", method="GET")
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}

    def confirm_order_by_mobile(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=self._confirm_order_url,
            method="POST",
            data=request_payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self._urlopen(request, timeout=self._timeout) as response:
                status_code = int(getattr(response, "status", 200))
                raw_body = response.read().decode("utf-8", errors="replace").strip()
            parsed_body = _try_parse_json_object(raw_body)
            return {
                "ok": 200 <= status_code < 300,
                "status_code": status_code,
                "body": parsed_body,
                "raw_body": None if parsed_body is not None else (raw_body or None),
            }
        except HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace").strip()
            parsed_error = _try_parse_json_object(raw_error)
            return {
                "ok": False,
                "status_code": int(exc.code),
                "body": parsed_error,
                "raw_body": None if parsed_error is not None else (raw_error or None),
            }

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
    pickup_region_name: str | None = None,
    pickup_city_id: int | str | None = None,
    pickup_city_name: str | None = None,
    pickup_pharmacy_id: int | str | None = None,
    pickup_pharmacy_name: str | None = None,
    pickup_contact: dict[str, object] | None = None,
    courier_contact: dict[str, object] | None = None,
    courier_address: dict[str, object] | None = None,
    payment_method: str | None = None,
    dont_call_me: bool | None = None,
    terms_accepted: bool | None = None,
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
        return _handle_courier_delivery(
            cart_session_id=resolved_session_id,
            cart_count=cart_count,
            cart_payload=cart_payload,
            reference_data=reference_data,
            pickup_contact=pickup_contact,
            courier_contact=courier_contact,
            courier_address=courier_address,
            payment_method=payment_method,
            dont_call_me=dont_call_me,
            terms_accepted=terms_accepted,
            comment=comment,
            reference_repository=effective_reference_repository,
        )

    if delivery_method != "pickup":
        return {
            "status": "validation_error",
            "errors": [{"field": "delivery_method", "message": "Unsupported delivery method"}],
            "cart_session_id": resolved_session_id,
        }

    available_regions = _available_regions_with_pharmacies(reference_data)
    if pickup_region_id is None and not (pickup_region_name or "").strip():
        return {
            "status": "pickup_contact_and_region",
            "cart_session_id": resolved_session_id,
            "available_regions": _extract_option_names(available_regions),
            "required_fields": {
                "first_name": "required|min:3",
                "last_name": "optional|min:3",
                "phone": "required|libphonenumber-compatible",
                "email": "optional|email-validator-compatible",
            },
        }

    selected_region = _resolve_option(
        available_regions,
        option_id=pickup_region_id,
        option_name=pickup_region_name,
    )
    if selected_region is None:
        return {
            "status": "validation_error",
            "errors": [
                {
                    "field": "pickup_region_name" if (pickup_region_name or "").strip() else "pickup_region_id",
                    "message": "Invalid region selection",
                }
            ],
            "cart_session_id": resolved_session_id,
        }
    normalized_region_id = int(selected_region["id"])
    selected_region_name = str(selected_region["name"])

    available_cities = _available_cities_for_region(reference_data, normalized_region_id)
    selected_city: dict[str, Any] | None = None
    direct_region_pharmacy: dict[str, Any] | None = None
    if pickup_pharmacy_id is not None or (pickup_pharmacy_name or "").strip():
        region_pharmacies = _pharmacies_for_region(reference_data, normalized_region_id)
        direct_region_pharmacy = _resolve_pharmacy(
            region_pharmacies,
            pharmacy_id=pickup_pharmacy_id,
            pharmacy_name=pickup_pharmacy_name,
        )

    if pickup_city_id is None and not (pickup_city_name or "").strip():
        if direct_region_pharmacy is not None:
            selected_city = _resolve_city_from_pharmacy(
                reference_data,
                region_id=normalized_region_id,
                pharmacy=direct_region_pharmacy,
            )
        elif len(available_cities) == 1:
            selected_city = available_cities[0]
        else:
            return {
                "status": "pickup_city_selection",
                "cart_session_id": resolved_session_id,
                "pickup_region_name": selected_region_name,
                "available_cities": _extract_option_names(available_cities),
            }
    else:
        selected_city = _resolve_option(
            available_cities,
            option_id=pickup_city_id,
            option_name=pickup_city_name,
        )
        if selected_city is None and direct_region_pharmacy is not None:
            selected_city = _resolve_city_from_pharmacy(
                reference_data,
                region_id=normalized_region_id,
                pharmacy=direct_region_pharmacy,
            )

    if selected_city is None:
        return {
            "status": "validation_error",
            "errors": [
                {
                    "field": "pickup_city_name" if (pickup_city_name or "").strip() else "pickup_city_id",
                    "message": "Invalid city selection",
                }
            ],
            "cart_session_id": resolved_session_id,
        }
    normalized_city_id = int(selected_city["id"])
    selected_city_name = str(selected_city["name"])

    available_pharmacies = _available_pharmacies(reference_data, normalized_region_id, normalized_city_id)
    selected_pharmacy: dict[str, Any] | None = None
    if pickup_pharmacy_id is None and not (pickup_pharmacy_name or "").strip():
        if len(available_pharmacies) == 1:
            selected_pharmacy = available_pharmacies[0]
        else:
            return {
                "status": "pickup_pharmacy_selection",
                "cart_session_id": resolved_session_id,
                "pickup_region_name": selected_region_name,
                "pickup_city_name": selected_city_name,
                "available_pharmacies": available_pharmacies,
            }
    else:
        selected_pharmacy = _resolve_pharmacy(
            available_pharmacies,
            pharmacy_id=pickup_pharmacy_id,
            pharmacy_name=pickup_pharmacy_name,
        )

    normalized_pharmacy_id = (
        _parse_positive_int(selected_pharmacy.get("id")) if isinstance(selected_pharmacy, dict) else None
    )
    if normalized_pharmacy_id is None:
        return {
            "status": "validation_error",
            "errors": [
                {
                    "field": "pickup_pharmacy_name"
                    if (pickup_pharmacy_name or "").strip()
                    else "pickup_pharmacy_id",
                    "message": "Invalid pharmacy selection",
                }
            ],
            "cart_session_id": resolved_session_id,
        }

    pickup_window = effective_reference_repository.get_pickup_timeslot(normalized_pharmacy_id)

    if not pickup_contact:
        return {
            "status": "pickup_contact",
            "cart_session_id": resolved_session_id,
            "pickup_window": pickup_window,
            "pickup": {
                "region_name": selected_region_name,
                "city_name": selected_city_name,
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

    normalized_contact = {
        "first_name": str(pickup_contact.get("first_name", "")).strip(),
        "last_name": str(pickup_contact.get("last_name", "")).strip(),
        "phone": str(pickup_contact.get("phone", "")).strip(),
        "email": str(pickup_contact.get("email", "")).strip(),
    }
    review_payload = {
        "cart": {
            "count": cart_count,
            "total": cart_payload.get("total"),
            "items": cart_payload.get("items") if isinstance(cart_payload.get("items"), list) else [],
        },
        "customer": normalized_contact,
        "delivery": {
            "method": "pickup",
            "region_name": selected_region_name,
            "city_name": selected_city_name,
            "pharmacy_id": normalized_pharmacy_id,
            "pharmacy": selected_pharmacy,
            "delivery_date": pickup_window.get("deliveryDate"),
            "delivery_from": pickup_window.get("from"),
            "delivery_to": pickup_window.get("to"),
            "cancellation_date": pickup_window.get("orderEnd"),
        },
        "comment": comment or "",
    }

    confirmation_started = (
        payment_method is not None or terms_accepted is not None or dont_call_me is not None
    )
    if not confirmation_started:
        return {
            "status": "pickup_confirmation_and_payment",
            "cart_session_id": resolved_session_id,
            "pickup_window": pickup_window,
            "pickup": {
                "region_name": selected_region_name,
                "city_name": selected_city_name,
                "pharmacy_id": normalized_pharmacy_id,
                "pharmacy": selected_pharmacy,
                "pickup_window": pickup_window,
                "contact": normalized_contact,
                "comment": comment or "",
            },
            "checkout_review": review_payload,
            "payment": {
                "required": True,
                "options": _PAYMENT_METHOD_OPTIONS,
            },
            "required_confirmations": {
                "dont_call_me": False,
                "terms_accepted": True,
                "terms_link": "https://front.apteka.md/ru/news/polizovateliskoe-soglashenie",
                "pickup_no_call_text": (
                    "Не звоните мне для подтверждения заказа! Я проверил(а) свой заказ, "
                    "адрес доставки и приду за заказом после СМС из аптеки"
                ),
                "courier_no_call_text": (
                    "Не звоните мне для подтверждения заказа! Я проверил(а) свой заказ."
                ),
            },
        }

    validation_errors = _validate_confirmation_fields(
        payment_method=payment_method,
        terms_accepted=terms_accepted,
    )
    if validation_errors:
        return {
            "status": "validation_error",
            "errors": validation_errors,
            "cart_session_id": resolved_session_id,
        }

    confirm_payload = _build_pickup_confirm_payload(
        payment_method=str(payment_method).strip(),
        dont_call_me=bool(dont_call_me),
        comment=comment or "",
        contact=normalized_contact,
        pickup_window=pickup_window,
        pharmacy_id=normalized_pharmacy_id,
    )
    try:
        confirm_response = effective_reference_repository.confirm_order_by_mobile(confirm_payload)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "order_submission_failed",
            "cart_session_id": resolved_session_id,
            "error": str(exc),
            "confirm_request": confirm_payload,
        }

    return {
        "status": "order_submitted",
        "cart_session_id": resolved_session_id,
        "pickup_window": pickup_window,
        "pickup": {
            "region_name": selected_region_name,
            "city_name": selected_city_name,
            "pharmacy_id": normalized_pharmacy_id,
            "pharmacy": selected_pharmacy,
            "pickup_window": pickup_window,
            "contact": normalized_contact,
            "comment": comment or "",
        },
        "checkout_review": review_payload,
        "confirm_request": confirm_payload,
        "confirm_response": confirm_response,
    }


def _handle_courier_delivery(
    *,
    cart_session_id: str,
    cart_count: int,
    cart_payload: dict[str, object],
    reference_data: dict[str, list[dict[str, Any]]],
    pickup_contact: dict[str, object] | None,
    courier_contact: dict[str, object] | None,
    courier_address: dict[str, object] | None,
    payment_method: str | None,
    dont_call_me: bool | None,
    terms_accepted: bool | None,
    comment: str | None,
    reference_repository: CheckoutReferenceRepository,
) -> dict[str, object]:
    if courier_address is not None and not isinstance(courier_address, dict):
        return {
            "status": "validation_error",
            "errors": [{"field": "courier_address", "message": "Courier address must be an object"}],
            "cart_session_id": cart_session_id,
        }

    if comment is not None and not isinstance(comment, str):
        return {
            "status": "validation_error",
            "errors": [{"field": "comment", "message": "Comment must be text"}],
            "cart_session_id": cart_session_id,
        }

    address_payload = courier_address or {}
    available_regions = _all_regions(reference_data)
    selected_region = _resolve_option(
        available_regions,
        option_id=address_payload.get("region_id"),
        option_name=str(address_payload.get("region_name") or ""),
    )
    if selected_region is None:
        return {
            "status": "courier_contact_and_region",
            "cart_session_id": cart_session_id,
            "available_regions": _extract_option_names(available_regions),
            "required_fields": {
                "first_name": "required|min:3",
                "last_name": "optional|min:3",
                "phone": "required|libphonenumber-compatible",
                "email": "optional|email-validator-compatible",
            },
            "required_address_fields": {
                "region_name": "required",
                "city_name": "required",
                "street": "required",
                "house_number": "required",
            },
            "optional_address_fields": ["apartment", "entrance", "floor", "intercom_code"],
        }

    normalized_region_id = int(selected_region["id"])
    selected_region_name = str(selected_region["name"])
    available_cities = _available_courier_cities_for_region(reference_data, normalized_region_id)
    selected_city = _resolve_option(
        available_cities,
        option_id=address_payload.get("city_id"),
        option_name=str(address_payload.get("city_name") or ""),
    )
    if selected_city is None:
        return {
            "status": "courier_city_selection",
            "cart_session_id": cart_session_id,
            "courier_region_name": selected_region_name,
            "available_cities": _extract_option_names(available_cities),
        }

    selected_city_name = str(selected_city["name"])
    selected_contact = (
        courier_contact
        if isinstance(courier_contact, dict)
        else (pickup_contact if isinstance(pickup_contact, dict) else None)
    )
    if selected_contact is None:
        return {
            "status": "courier_contact_and_address",
            "cart_session_id": cart_session_id,
            "courier": {
                "region_name": selected_region_name,
                "city_name": selected_city_name,
            },
            "required_fields": {
                "first_name": "required|min:3",
                "last_name": "optional|min:3",
                "phone": "required|libphonenumber-compatible",
                "email": "optional|email-validator-compatible",
            },
            "required_address_fields": {
                "street": "required",
                "house_number": "required",
            },
            "optional_address_fields": ["apartment", "entrance", "floor", "intercom_code"],
        }

    normalized_address = _normalize_courier_address(address_payload)
    errors = [
        *_validate_pickup_contact(selected_contact),
        *_validate_courier_address(normalized_address),
    ]
    if errors:
        return {
            "status": "validation_error",
            "errors": errors,
            "cart_session_id": cart_session_id,
        }

    normalized_contact = {
        "first_name": str(selected_contact.get("first_name", "")).strip(),
        "last_name": str(selected_contact.get("last_name", "")).strip(),
        "phone": str(selected_contact.get("phone", "")).strip(),
        "email": str(selected_contact.get("email", "")).strip(),
    }
    review_payload = {
        "cart": {
            "count": cart_count,
            "total": cart_payload.get("total"),
            "items": cart_payload.get("items") if isinstance(cart_payload.get("items"), list) else [],
        },
        "customer": normalized_contact,
        "delivery": {
            "method": "courier_delivery",
            "region_name": selected_region_name,
            "city_name": selected_city_name,
            "street": normalized_address["street"],
            "house_number": normalized_address["house_number"],
            "apartment": normalized_address["apartment"],
            "entrance": normalized_address["entrance"],
            "floor": normalized_address["floor"],
            "intercom_code": normalized_address["intercom_code"],
        },
        "comment": comment or "",
    }
    confirmation_started = (
        payment_method is not None or terms_accepted is not None or dont_call_me is not None
    )
    if not confirmation_started:
        return {
            "status": "courier_ready_for_submission",
            "cart_session_id": cart_session_id,
            "courier": {
                "region_name": selected_region_name,
                "city_name": selected_city_name,
                "contact": normalized_contact,
                "address": normalized_address,
                "comment": comment or "",
            },
            "checkout_review": review_payload,
            "payment": {"required": True, "options": _PAYMENT_METHOD_OPTIONS},
            "required_confirmations": {
                "dont_call_me": False,
                "terms_accepted": True,
                "terms_link": "https://front.apteka.md/ru/news/polizovateliskoe-soglashenie",
            },
        }

    validation_errors = _validate_confirmation_fields(
        payment_method=payment_method,
        terms_accepted=terms_accepted,
    )
    if validation_errors:
        return {
            "status": "validation_error",
            "errors": validation_errors,
            "cart_session_id": cart_session_id,
        }

    confirm_payload = _build_courier_confirm_payload(
        payment_method=str(payment_method).strip(),
        dont_call_me=bool(dont_call_me),
        comment=comment or "",
        contact=normalized_contact,
        address=normalized_address,
    )
    try:
        confirm_response = reference_repository.confirm_order_by_mobile(confirm_payload)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "order_submission_failed",
            "cart_session_id": cart_session_id,
            "error": str(exc),
            "confirm_request": confirm_payload,
        }

    return {
        "status": "order_submitted",
        "cart_session_id": cart_session_id,
        "courier": {
            "region_name": selected_region_name,
            "city_name": selected_city_name,
            "contact": normalized_contact,
            "address": normalized_address,
            "comment": comment or "",
        },
        "checkout_review": review_payload,
        "confirm_request": confirm_payload,
        "confirm_response": confirm_response,
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


def _normalize_name(value: str | None) -> str:
    return str(value or "").strip().casefold()


def _extract_option_names(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("name") or "").strip() for item in items if str(item.get("name") or "").strip()]


def _resolve_option(
    items: list[dict[str, Any]],
    *,
    option_id: int | str | None,
    option_name: str | None,
) -> dict[str, Any] | None:
    normalized_id = _parse_positive_int(option_id)
    if normalized_id is not None:
        for item in items:
            if _parse_positive_int(item.get("id")) == normalized_id:
                return item

    normalized_name = _normalize_name(option_name)
    if normalized_name:
        for item in items:
            if _normalize_name(str(item.get("name") or "")) == normalized_name:
                return item
    return None


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


def _all_regions(reference_data: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        _to_display_option(region)
        for region in reference_data["regions"]
        if _parse_positive_int(region.get("id")) is not None
    ]


def _available_cities_for_region(
    reference_data: dict[str, list[dict[str, Any]]],
    region_id: int,
) -> list[dict[str, Any]]:
    option_names_by_id: dict[int, str] = {}
    option_order: list[int] = []

    for city in reference_data["cities_without_regions"]:
        if _parse_positive_int(city.get("region_id")) != region_id:
            continue
        city_id = _parse_positive_int(city.get("id"))
        if city_id is None:
            continue
        city_name = _extract_name(city).strip()
        if not city_name:
            continue
        if city_id not in option_names_by_id:
            option_names_by_id[city_id] = city_name
            option_order.append(city_id)

    pharmacy_city_ids: set[int] = set()
    for pharmacy in reference_data["pharmacies"]:
        normalized_region_id = None
        region_node = pharmacy.get("region")
        if isinstance(region_node, dict):
            normalized_region_id = _parse_positive_int(region_node.get("id"))
        if normalized_region_id is None:
            normalized_region_id = _parse_positive_int(pharmacy.get("region_id"))
        if normalized_region_id != region_id:
            continue

        city_id = _extract_pharmacy_city_id(pharmacy, region_id)
        if city_id is None:
            continue

        pharmacy_city_ids.add(city_id)
        if city_id in option_names_by_id:
            continue

        fallback_name = _extract_pharmacy_location_name(pharmacy, city_id).strip()
        if fallback_name:
            option_names_by_id[city_id] = fallback_name
            option_order.append(city_id)

    return [
        {"id": city_id, "name": option_names_by_id[city_id]}
        for city_id in option_order
        if city_id in pharmacy_city_ids
    ]


def _available_courier_cities_for_region(
    reference_data: dict[str, list[dict[str, Any]]],
    region_id: int,
) -> list[dict[str, Any]]:
    cities: list[dict[str, Any]] = []
    for city in reference_data["cities_without_regions"]:
        if _parse_positive_int(city.get("region_id")) != region_id:
            continue
        city_id = _parse_positive_int(city.get("id"))
        if city_id is None:
            continue
        city_name = _extract_name(city).strip()
        if not city_name:
            continue
        cities.append({"id": city_id, "name": city_name})
    return cities


def _extract_pharmacy_location_name(pharmacy: dict[str, Any], city_id: int) -> str:
    sector_node = pharmacy.get("sector")
    if isinstance(sector_node, dict):
        sector_id = _parse_positive_int(sector_node.get("id"))
        if sector_id == city_id:
            return _extract_name(sector_node)

    city_node = pharmacy.get("city")
    if isinstance(city_node, dict):
        normalized_city_id = _parse_positive_int(city_node.get("id"))
        if normalized_city_id == city_id:
            return _extract_name(city_node)
    return ""


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


def _pharmacies_for_region(
    reference_data: dict[str, list[dict[str, Any]]],
    region_id: int,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for pharmacy in reference_data["pharmacies"]:
        normalized_region_id = None
        region_node = pharmacy.get("region")
        if isinstance(region_node, dict):
            normalized_region_id = _parse_positive_int(region_node.get("id"))
        if normalized_region_id is None:
            normalized_region_id = _parse_positive_int(pharmacy.get("region_id"))
        if normalized_region_id == region_id:
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


def _resolve_pharmacy(
    pharmacies: list[dict[str, Any]],
    *,
    pharmacy_id: int | str | None,
    pharmacy_name: str | None,
) -> dict[str, Any] | None:
    normalized_id = _parse_positive_int(pharmacy_id)
    by_id = _find_pharmacy(pharmacies, normalized_id)
    if by_id is not None:
        return by_id

    normalized_name = _normalize_name(pharmacy_name)
    if not normalized_name:
        return None
    for pharmacy in pharmacies:
        if _normalize_name(_extract_name(pharmacy)) == normalized_name:
            return pharmacy
    return None


def _resolve_city_from_pharmacy(
    reference_data: dict[str, list[dict[str, Any]]],
    *,
    region_id: int,
    pharmacy: dict[str, Any],
) -> dict[str, Any] | None:
    city_id = _extract_pharmacy_city_id(pharmacy, region_id)
    if city_id is None:
        return None
    available_cities = _available_cities_for_region(reference_data, region_id)
    by_city_id = _resolve_option(
        available_cities,
        option_id=city_id,
        option_name=None,
    )
    if by_city_id is not None:
        return by_city_id
    fallback_name = _extract_pharmacy_location_name(pharmacy, city_id).strip()
    if fallback_name:
        return {"id": city_id, "name": fallback_name}
    return None


def _extract_pharmacy_city_id(pharmacy: dict[str, Any], region_id: int) -> int | None:
    del region_id
    sector_node = pharmacy.get("sector")
    if isinstance(sector_node, dict):
        sector_id = _parse_positive_int(sector_node.get("id"))
        if sector_id is not None:
            return sector_id

    city_node = pharmacy.get("city")
    if isinstance(city_node, dict):
        city_id = _parse_positive_int(city_node.get("id"))
        if city_id is not None:
            return city_id

    for key in ("city_id", "locality_id", "settlement_id"):
        city_id = _parse_positive_int(pharmacy.get(key))
        if city_id is not None:
            return city_id

    return None


def _validate_pickup_contact(contact: dict[str, object]) -> list[dict[str, str]]:
    service = _build_checkout_validation_service()
    return service.validate_pickup_contact(CheckoutContact.from_payload(contact))


def _normalize_courier_address(address: dict[str, object]) -> dict[str, str]:
    service = _build_checkout_validation_service()
    return service.normalize_courier_address(address)


def _validate_courier_address(address: dict[str, str]) -> list[dict[str, str]]:
    service = _build_checkout_validation_service()
    return service.validate_courier_address(service.normalize_courier_address(address))


def _is_valid_phone(phone: str) -> bool:
    normalized_phone = _normalize_international_phone(phone)
    if normalized_phone is None or not _SIMPLE_PHONE_PATTERN.match(normalized_phone):
        return False
    return _matches_allowed_phone_rule(normalized_phone)


def _is_valid_email(email: str) -> bool:
    try:
        from email_validator import validate_email  # type: ignore

        validate_email(email)
        return True
    except Exception:  # noqa: BLE001
        return bool(_SIMPLE_EMAIL_PATTERN.match(email))


def _validate_confirmation_fields(
    *,
    payment_method: str | None,
    terms_accepted: bool | None,
) -> list[dict[str, str]]:
    service = _build_checkout_validation_service()
    return service.validate_confirmation_fields(
        payment_method=payment_method,
        terms_accepted=terms_accepted,
    )


def _build_pickup_confirm_payload(
    *,
    payment_method: str,
    dont_call_me: bool,
    comment: str,
    contact: dict[str, str],
    pickup_window: dict[str, Any],
    pharmacy_id: int,
) -> dict[str, object]:
    return {
        "orderType": "mobile",
        "note": comment or None,
        "dontCallMe": dont_call_me,
        "delivery": {
            "firstName": contact["first_name"],
            "lastName": contact["last_name"] or None,
            "type": "PICK_UP",
            "pharmacy_id": pharmacy_id,
            "phone": contact["phone"],
            "email": contact["email"] or None,
            "deliveryWindow": {
                "deliveryDate": pickup_window.get("deliveryDate"),
                "from": pickup_window.get("from"),
                "to": pickup_window.get("to"),
            },
        },
        "payment": {
            "type": payment_method,
        },
    }


def _build_courier_confirm_payload(
    *,
    payment_method: str,
    dont_call_me: bool,
    comment: str,
    contact: dict[str, str],
    address: dict[str, str],
) -> dict[str, object]:
    return {
        "orderType": "mobile",
        "note": comment or None,
        "dontCallMe": dont_call_me,
        "delivery": {
            "firstName": contact["first_name"],
            "lastName": contact["last_name"] or None,
            "type": "COURIER_DELIVERY",
            "phone": contact["phone"],
            "email": contact["email"] or None,
            "address": {
                "street": address["street"],
                "house_number": address["house_number"],
                "apartment": address["apartment"] or None,
                "entrance": address["entrance"] or None,
                "floor": address["floor"] or None,
                "intercom_code": address["intercom_code"] or None,
            },
        },
        "payment": {"type": payment_method},
    }


def _load_cached_checkout_reference_data(
    repository: CheckoutReferenceRepository,
) -> dict[str, list[dict[str, Any]]]:
    state = _get_checkout_reference_cache_state()
    with state.lock:
        now = _monotonic()
        if state.payload is not None:
            expires_at, payload = state.payload
            if now < expires_at:
                return payload

        payload = {
            "regions": repository.get_regions(),
            "cities_without_regions": repository.get_cities_without_regions(),
            "pharmacies": repository.get_pharmacies(),
        }
        ttl_seconds = _get_checkout_reference_cache_ttl_seconds()
        state.payload = (now + ttl_seconds, payload)
        return payload


def _clear_checkout_reference_cache() -> None:
    state = _get_checkout_reference_cache_state()
    with state.lock:
        state.payload = None


def _build_checkout_validation_service() -> CheckoutValidationService:
    return CheckoutValidationService(
        phone_validator=_is_valid_phone,
        email_validator=_is_valid_email,
        payment_method_ids=set(_PAYMENT_METHOD_IDS),
    )


@lru_cache(maxsize=1)
def _get_checkout_reference_cache_state() -> _CheckoutReferenceCacheState:
    return _CheckoutReferenceCacheState(lock=Lock())


def _get_checkout_reference_cache_ttl_seconds() -> float:
    settings = get_settings()
    ttl_seconds = float(
        getattr(
            settings,
            "mcp_checkout_reference_cache_ttl_seconds",
            CHECKOUT_REFERENCE_CACHE_TTL_SECONDS,
        )
    )
    if ttl_seconds <= 0:
        return CHECKOUT_REFERENCE_CACHE_TTL_SECONDS
    return ttl_seconds


def _extract_collection(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _try_parse_json_object(raw_payload: str) -> dict[str, Any] | None:
    if not raw_payload:
        return None
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_international_phone(phone: str) -> str | None:
    stripped = str(phone or "").strip()
    if not stripped.startswith("+"):
        return None
    digits_only = _NON_DIGITS_PATTERN.sub("", stripped)
    if not digits_only:
        return None
    return f"+{digits_only}"


def _matches_allowed_phone_rule(normalized_phone: str) -> bool:
    rules = _load_allowed_phone_rules()
    digits = normalized_phone[1:]
    for rule in rules:
        dial_code = str(rule.get("dial_code") or "")
        if not dial_code or not digits.startswith(dial_code):
            continue
        local_length = len(digits) - len(dial_code)
        min_length = int(rule.get("min_length") or 0)
        max_length = int(rule.get("max_length") or 0)
        if min_length <= local_length <= max_length:
            return True
    return False


def _load_allowed_phone_rules() -> list[dict[str, Any]]:
    global _ALLOWED_PHONE_RULES_CACHE
    with _ALLOWED_PHONE_RULES_LOCK:
        if _ALLOWED_PHONE_RULES_CACHE is None:
            payload = json.loads(_ALLOWED_PHONE_CODES_PATH.read_text(encoding="utf-8"))
            parsed = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
            _ALLOWED_PHONE_RULES_CACHE = sorted(
                parsed,
                key=lambda item: len(str(item.get("dial_code") or "")),
                reverse=True,
            )
        return _ALLOWED_PHONE_RULES_CACHE
