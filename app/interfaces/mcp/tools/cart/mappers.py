"""Cart payload mappers and normalizers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.domain.cart.entities import CartItem, CartSnapshot


def map_cart_snapshot(payload: Any) -> CartSnapshot:
    node = payload
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        node = payload["data"]

    if not isinstance(node, dict):
        return CartSnapshot(items=[], count=0, total=None)

    items_payload = node.get("items")
    items: list[CartItem] = []
    if isinstance(items_payload, list):
        for raw_item in items_payload:
            if not isinstance(raw_item, dict):
                continue
            product_id = str(
                raw_item.get("product_id")
                or raw_item.get("productId")
                or raw_item.get("id")
                or raw_item.get("sku")
                or ""
            ).strip()
            if not product_id:
                continue
            quantity_raw = raw_item.get("quantity") or raw_item.get("count") or 1
            try:
                quantity = int(quantity_raw)
            except (TypeError, ValueError):
                quantity = 1
            if quantity < 0:
                quantity = 0
            raw_name = raw_item.get("name")
            raw_manufacturer = raw_item.get("manufacturer")
            raw_price = raw_item.get("price")
            raw_discount_price = raw_item.get("discount_price")
            raw_image_url = raw_item.get("image_url") or raw_item.get("imageUrl")
            name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
            manufacturer = (
                raw_manufacturer.strip()
                if isinstance(raw_manufacturer, str) and raw_manufacturer.strip()
                else None
            )
            image_url = normalize_image_url(raw_image_url)
            price = coerce_money(raw_price)
            discount_price = coerce_money(raw_discount_price)
            items.append(
                CartItem(
                    product_id=product_id,
                    quantity=quantity,
                    name=name,
                    price=price,
                    discount_price=discount_price,
                    manufacturer=manufacturer,
                    image_url=image_url,
                )
            )

    count_raw = node.get("count")
    if count_raw is None:
        count = len(items)
    else:
        try:
            count = int(count_raw)
        except (TypeError, ValueError):
            count = len(items)

    total_raw = node.get("total")
    if total_raw is None:
        total_raw = node.get("totalAmount")

    total: Decimal | None
    if total_raw is None:
        computed_total = Decimal("0")
        has_priced_items = False
        for item in items:
            unit_price = item.discount_price if item.discount_price is not None else item.price
            if unit_price is None:
                continue
            has_priced_items = True
            computed_total += unit_price * Decimal(max(0, item.quantity))
        if has_priced_items:
            total = computed_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            total = None
    else:
        try:
            total = Decimal(str(total_raw)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (TypeError, ValueError, InvalidOperation):
            total = None

    return CartSnapshot(items=items, count=count, total=total)


def normalize_item_meta_payload(raw_payload: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    raw_name = raw_payload.get("name")
    if isinstance(raw_name, str):
        name = raw_name.strip()
        if name:
            payload["name"] = name

    raw_manufacturer = raw_payload.get("manufacturer")
    if isinstance(raw_manufacturer, str):
        manufacturer = raw_manufacturer.strip()
        if manufacturer:
            payload["manufacturer"] = manufacturer

    raw_price = raw_payload.get("price")
    normalized_price = coerce_money(raw_price)
    if normalized_price is not None:
        payload["price"] = money_to_wire(normalized_price)

    raw_discount_price = raw_payload.get("discount_price")
    normalized_discount_price = coerce_money(raw_discount_price)
    if normalized_discount_price is not None:
        payload["discount_price"] = money_to_wire(normalized_discount_price)

    raw_image_url = raw_payload.get("image_url") or raw_payload.get("imageUrl")
    image_url = normalize_image_url(raw_image_url)
    if image_url is not None:
        payload["image_url"] = image_url

    return payload


def normalize_image_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    image_url = value.strip()
    if not image_url:
        return None
    lowered = image_url.lower()
    if lowered.startswith("javascript:"):
        return None
    if lowered.startswith("data:"):
        return image_url
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return image_url
    if image_url.startswith("/"):
        return image_url
    return None


def coerce_money(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    return None


def money_to_wire(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
