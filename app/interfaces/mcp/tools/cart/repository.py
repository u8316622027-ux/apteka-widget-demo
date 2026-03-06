"""HTTP repository for cart API."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen as default_urlopen

from app.domain.cart.entities import CartToken, CartSnapshot
from app.domain.cart.repository import CartApiRepository
from app.interfaces.mcp.tools.apteka_urls import build_front_url
from app.interfaces.mcp.tools.cart.mappers import (
    map_cart_snapshot,
    money_to_wire,
    normalize_item_meta_payload,
)

APTEKA_CART_PATH = "/cart"


class AptekaCartRepository(CartApiRepository):
    """HTTP-backed repository for apteka cart API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = (base_url or build_front_url(APTEKA_CART_PATH)).rstrip("/")
        self._timeout = timeout
        self._urlopen = urlopen

    def create_cart(self) -> CartToken:
        request = Request(url=self._base_url, method="GET")
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        access_token = str(payload.get("accessToken") or "").strip()
        token_type = str(payload.get("tokenType") or "Bearer").strip() or "Bearer"
        if not access_token:
            raise ValueError("cart token is missing in apteka response")

        return CartToken(access_token=access_token, token_type=token_type)

    def get_cart(self, token: CartToken) -> CartSnapshot:
        request = Request(
            url=self._base_url,
            method="GET",
            headers={"Authorization": f"{token.token_type} {token.access_token}"},
        )
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return map_cart_snapshot(payload)

    def add_item(
        self,
        token: CartToken,
        *,
        product_id: str,
        quantity: int,
        item_meta: dict[str, object] | None = None,
    ) -> CartSnapshot:
        if quantity <= 0:
            return self.get_cart(token)
        payload: dict[str, object] = {
            "product_id": product_id,
            "quantity": quantity,
            "json": True,
        }
        if item_meta:
            payload.update(normalize_item_meta_payload(item_meta))
        request_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=f"{self._base_url}/add",
            method="POST",
            data=request_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"{token.token_type} {token.access_token}",
            },
        )
        try:
            with self._urlopen(request, timeout=self._timeout):
                return self.get_cart(token)
        except HTTPError as exc:
            if int(getattr(exc, "code", 0)) not in {409, 422}:
                raise
            current = self.get_cart(token)
            merged_items: list[tuple[str, int]] = []
            current_quantity = 0
            meta_payload: dict[str, dict[str, object]] = {}
            for item in current.items:
                if item.quantity <= 0:
                    continue
                merged_items.append((item.product_id, item.quantity))
                item_meta_payload: dict[str, object] = {}
                if item.name is not None:
                    item_meta_payload["name"] = item.name
                if item.manufacturer is not None:
                    item_meta_payload["manufacturer"] = item.manufacturer
                if item.price is not None:
                    item_meta_payload["price"] = money_to_wire(item.price)
                if item.discount_price is not None:
                    item_meta_payload["discount_price"] = money_to_wire(item.discount_price)
                if item.image_url is not None:
                    item_meta_payload["image_url"] = item.image_url
                if item_meta_payload:
                    meta_payload[item.product_id] = item_meta_payload
                if item.product_id == product_id:
                    current_quantity = item.quantity
            next_quantity = max(0, current_quantity + quantity)
            merged_by_product_id: dict[str, int] = {
                item_id: item_qty for item_id, item_qty in merged_items
            }
            if next_quantity <= 0:
                merged_by_product_id.pop(product_id, None)
                meta_payload.pop(product_id, None)
            else:
                merged_by_product_id[product_id] = next_quantity
            if item_meta:
                meta_payload[product_id] = normalize_item_meta_payload(item_meta)
            return self.update_items(
                token,
                items=list(merged_by_product_id.items()),
                item_meta_by_product_id=meta_payload or None,
            )

    def update_items(
        self,
        token: CartToken,
        *,
        items: list[tuple[str, int]],
        item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
    ) -> CartSnapshot:
        update_items_payload: list[dict[str, object]] = []
        for product_id, quantity in items:
            row: dict[str, object] = {"product_id": product_id, "quantity": quantity}
            if item_meta_by_product_id and product_id in item_meta_by_product_id:
                row.update(normalize_item_meta_payload(item_meta_by_product_id[product_id]))
            update_items_payload.append(row)
        request_payload = json.dumps(
            {"items": update_items_payload, "json": True},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=f"{self._base_url}/update",
            method="POST",
            data=request_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"{token.token_type} {token.access_token}",
            },
        )
        with self._urlopen(request, timeout=self._timeout):
            return self.get_cart(token)
