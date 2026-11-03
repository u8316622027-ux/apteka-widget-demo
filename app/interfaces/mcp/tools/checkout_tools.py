"""Review and explicitly submit an order using the existing user's cart."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import asdict
from decimal import Decimal
from time import monotonic
from typing import Any

from app.domain.cart.service import _session_update_lock
from app.domain.checkout.entities import CheckoutContact, CourierAddress
from app.domain.checkout.service import CheckoutValidationService
from app.interfaces.mcp.tools.cart_tools import (
    AptekaCartRepository,
    _build_default_token_store,
    check_cart,
)
from app.interfaces.mcp.tools.checkout_api import AptekaCheckoutClient, OrderValidationError

PAYMENT_TYPES = {"cash_on_receipt": "cash", "card_on_receipt": "card"}
PAYMENT_METHODS = set(PAYMENT_TYPES)
_REVIEWS: dict[str, dict[str, Any]] = {}
_REVIEW_LOCK = threading.RLock()
REVIEW_TTL = 900
MAX_REVIEWS = 1024


def _fingerprint(cart):
    return hashlib.sha256(
        json.dumps(
            {
                "items": sorted(cart["items"], key=lambda item: item["product_id"]),
                "total": cart["total"],
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def _required_option(options, value, field):
    option = next((item for item in options if str(item["id"]) == str(value)), None)
    if option is None:
        raise ValueError(f"Invalid {field}; choose an available option")
    return option


def checkout_order(arguments, *, repository=None, token_store=None, client=None):
    """Options -> review -> submit; a server-held review binds the order to the cart."""
    session_id = str(arguments.get("cart_session_id") or "").strip()
    if not session_id:
        raise ValueError("cart_session_id is required; use add_to_cart to create a cart first")
    store = token_store or _build_default_token_store()
    token = store.get_token(session_id)
    if token is None:
        raise ValueError("Cart session expired; reopen the cart before checkout")
    repo = repository or AptekaCartRepository()
    api = client or AptekaCheckoutClient()
    action = arguments.get("action") or "options"
    language = "ro" if str(arguments.get("language", "ru")).startswith("ro") else "ru"
    if action == "submit":
        return _submit(arguments, session_id, token, repo, store, api)
    cart = check_cart(cart_session_id=session_id, repository=repo, token_store=store)
    if not cart["items"]:
        return {"status": "cart_empty", "cart_session_id": session_id, "cart": cart}
    references = api.reference_data(language)
    if action == "delivery":
        method = arguments.get("delivery_method")
        if method == "pickup":
            destination = _required_option(
                references["pharmacies"], arguments.get("pharmacy_id"), "pharmacy"
            )
        elif method == "courier":
            destination = _required_option(
                references["regions"], arguments.get("region_id"), "region"
            )
        else:
            raise ValueError("Choose pickup or courier delivery")
        return {
            "status": "delivery_windows",
            "cart_session_id": session_id,
            "windows": api.delivery_windows(method, destination["id"], language),
        }
    if action == "options":
        return {
            "status": "delivery_method_selection",
            "cart_session_id": session_id,
            "cart": cart,
            "language": language,
            **references,
        }
    if action != "review":
        raise ValueError("Unsupported checkout action")
    order, preview = _build_review(arguments, cart, references, api, language)
    confirmation_id = secrets.token_urlsafe(32)
    with _REVIEW_LOCK:
        now = monotonic()
        for key in list(_REVIEWS):
            if _REVIEWS[key]["expires"] <= now:
                del _REVIEWS[key]
        if len(_REVIEWS) >= MAX_REVIEWS:
            raise ValueError("Checkout is busy; try again later")
        _REVIEWS[confirmation_id] = {
            "expires": now + REVIEW_TTL,
            "session_id": session_id,
            "fingerprint": _fingerprint(cart),
            "order": order,
            "preview": preview,
            "language": language,
            "state": "review",
            "lock": threading.Lock(),
        }
    return {
        "status": "review",
        "cart_session_id": session_id,
        "confirmation_id": confirmation_id,
        "review": preview,
    }


def _build_review(args, cart, references, api, language):
    contact = CheckoutContact.from_payload(args.get("contact") or {})
    validator = CheckoutValidationService(payment_method_ids=PAYMENT_METHODS)
    errors = validator.validate_pickup_contact(contact)
    payment = str(args.get("payment_method") or "")
    if payment not in PAYMENT_METHODS:
        errors.append({"message": "Choose a payment method"})
    if errors:
        raise ValueError("; ".join(error["message"] for error in errors))
    method = args.get("delivery_method")
    fee = Decimal("0")
    delivery = {
        "firstName": contact.first_name,
        "lastName": contact.last_name,
        "phone": contact.phone,
        "email": contact.email or None,
    }
    if method == "pickup":
        pharmacy = _required_option(references["pharmacies"], args.get("pharmacy_id"), "pharmacy")
        destination_id = pharmacy["id"]
        delivery.update(type="pick-up", pharmacy_id=destination_id)
        destination = f"{pharmacy['name']}, {pharmacy['address']}"
    elif method == "courier":
        region = _required_option(references["regions"], args.get("region_id"), "region")
        city = _required_option(
            [item for item in references["cities"] if item["region_id"] == region["id"]],
            args.get("city_id"),
            "city",
        )
        address = CourierAddress.from_payload(args.get("address") or {})
        errors = validator.validate_courier_address(address)
        if errors:
            raise ValueError("; ".join(error["message"] for error in errors))
        destination_id = region["id"]
        delivery.update(
            type="target",
            address_id=None,
            address={
                "region_id": region["id"],
                "sector_id": city["id"],
                "city": city["name"],
                "street": address.street,
                "building": address.house_number,
                "apartment": address.apartment,
                "entrance": address.entrance,
                "floor": address.floor,
                "intercomCode": address.intercom_code,
            },
        )
        destination = f"{region['name']}, {city['name']}, {address.street} {address.house_number}"
        fee = Decimal(str(region.get("delivery_cost") or 0))
        free_threshold = region.get("free_shipping_cost")
        if free_threshold and Decimal(str(cart["total"])) >= Decimal(str(free_threshold)):
            fee = Decimal("0")
    else:
        raise ValueError("Choose pickup or courier delivery")
    windows = api.delivery_windows(method, destination_id, language)
    if not windows:
        raise ValueError("No delivery window available; choose another destination")
    requested_window = args.get("delivery_window") or windows[0]
    selected_window = next(
        (
            window
            for window in windows
            if all(
                window.get(key) == requested_window.get(key)
                for key in ("deliveryDate", "from", "to")
            )
        ),
        None,
    )
    if selected_window is None:
        raise ValueError("Delivery window is no longer available; review the order again")
    requested_window = selected_window
    delivery["deliveryWindow"] = {
        key: requested_window[key] for key in ("deliveryDate", "from", "to")
    }
    if cart["total"] is None:
        raise ValueError("Cart total is unavailable; refresh the cart")
    order = {
        "orderType": "ai apps",
        "note": str(args.get("comment") or "").strip(),
        "dontCallMe": bool(args.get("dont_call_me")),
        "delivery": delivery,
        "payment": {"type": PAYMENT_TYPES[payment], "useBonuses": False},
    }
    preview = {
        "items": cart["items"],
        "subtotal": cart["total"],
        "delivery_fee": float(fee),
        "total": float(Decimal(str(cart["total"])) + fee),
        "contact": asdict(contact),
        "delivery_method": method,
        "destination": destination,
        "delivery_window": requested_window,
        "available_windows": windows,
        "payment_method": payment,
        "comment": order["note"],
        "checkout_input": {
            "delivery_method": method,
            "region_id": pharmacy["region_id"] if method == "pickup" else region["id"],
            "city_id": pharmacy["city_id"] if method == "pickup" else city["id"],
            "pharmacy_id": pharmacy["id"] if method == "pickup" else None,
            "contact": asdict(contact),
            "address": asdict(address) if method == "courier" else {},
            "payment_method": payment,
            "comment": order["note"],
        },
    }
    return order, preview


def _submit(args, session_id, token, repo, store, api):
    if args.get("terms_accepted") is not True:
        raise ValueError("Accept the terms before submitting the order")
    with _REVIEW_LOCK:
        review = _REVIEWS.get(str(args.get("confirmation_id") or ""))
    if not review or review["session_id"] != session_id or review["expires"] <= monotonic():
        raise ValueError("Review expired or does not belong to this cart; review the order again")
    with review["lock"], _session_update_lock(session_id):
        if review["state"] == "submitted":
            return review["result"]
        if review["state"] != "review":
            raise ValueError("Order status is uncertain; contact support before trying again")
        cart = check_cart(cart_session_id=session_id, repository=repo, token_store=store)
        if _fingerprint(cart) != review["fingerprint"]:
            raise ValueError("The cart has changed; review the order again")
        review["state"] = "submitting"
        # A validation rejection is definitive. Other failures keep the duplicate guard.
        try:
            order = api.send_order(token, review["order"], review["language"])
        except OrderValidationError:
            review["state"] = "review"
            raise
        result = {
            "status": "order_submitted",
            "cart_session_id": session_id,
            "order_id": str(order["id"]),
            "order_number": order.get("number"),
            "review": review["preview"],
        }
        review.update(state="submitted", result=result)
        return result
