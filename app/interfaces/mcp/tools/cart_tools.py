"""MCP cart tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from time import time
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen as default_urlopen

from app.core.config import get_settings
from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.domain.cart.repository import CartApiRepository, CartTokenStore
from app.domain.cart.service import CartService
from app.interfaces.mcp.tools.apteka_urls import build_front_url
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id

APTEKA_CART_PATH = "/cart"


@dataclass(slots=True)
class _TokenRecord:
    token: CartToken
    expires_at: float


class InMemoryCartTokenStore(CartTokenStore):
    """In-memory token store for local development and tests."""

    def __init__(self, *, ttl_seconds: int = 30 * 24 * 60 * 60) -> None:
        self._ttl_seconds = ttl_seconds
        self._records: dict[str, _TokenRecord] = {}

    def get_token(self, cart_session_id: str) -> CartToken | None:
        record = self._records.get(cart_session_id)
        if record is None:
            return None

        if record.expires_at < time():
            self._records.pop(cart_session_id, None)
            return None

        return record.token

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        self._records[cart_session_id] = _TokenRecord(
            token=token,
            expires_at=time() + self._ttl_seconds,
        )


class RedisCartTokenStore(CartTokenStore):
    """Redis-backed token store for shared sessions across instances."""

    def __init__(
        self, redis_client: Any, *, prefix: str = "cart:session", ttl_seconds: int = 604800
    ) -> None:
        self._redis = redis_client
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    def get_token(self, cart_session_id: str) -> CartToken | None:
        key = self._key(cart_session_id)
        raw = self._redis.get(key)
        if raw is None:
            return None

        if isinstance(raw, bytes):
            payload = json.loads(raw.decode("utf-8"))
        else:
            payload = json.loads(str(raw))

        access_token = str(payload.get("access_token") or "").strip()
        token_type = str(payload.get("token_type") or "Bearer").strip() or "Bearer"
        if not access_token:
            return None

        return CartToken(access_token=access_token, token_type=token_type)

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        key = self._key(cart_session_id)
        payload = json.dumps(
            {"access_token": token.access_token, "token_type": token.token_type},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self._redis.setex(key, self._ttl_seconds, payload)

    def _key(self, cart_session_id: str) -> str:
        return f"{self._prefix}:{cart_session_id}"


class UpstashRestCartTokenStore(CartTokenStore):
    """Upstash Redis REST-backed token store."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        prefix: str = "cart:session",
        ttl_seconds: int = 604800,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds
        self._timeout = timeout
        self._urlopen = urlopen

    def get_token(self, cart_session_id: str) -> CartToken | None:
        key = quote(self._key(cart_session_id), safe="")
        request = Request(
            url=f"{self._base_url}/get/{key}",
            method="GET",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        raw_value = payload.get("result")
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None

        try:
            token_payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return None

        # Some Upstash clients store wrapped payload:
        # {"value":"{\"access_token\":\"...\",\"token_type\":\"Bearer\"}","ex":604800}
        if isinstance(token_payload, dict) and isinstance(token_payload.get("value"), str):
            try:
                nested_payload = json.loads(str(token_payload["value"]))
            except json.JSONDecodeError:
                nested_payload = None
            if isinstance(nested_payload, dict):
                token_payload = nested_payload

        access_token = str(token_payload.get("access_token") or "").strip()
        token_type = str(token_payload.get("token_type") or "Bearer").strip() or "Bearer"
        if not access_token:
            return None

        return CartToken(access_token=access_token, token_type=token_type)

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        key = quote(self._key(cart_session_id), safe="")
        value = json.dumps(
            {"access_token": token.access_token, "token_type": token.token_type},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request_payload = json.dumps(
            {"value": value, "ex": self._ttl_seconds},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=f"{self._base_url}/set/{key}",
            data=request_payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        with self._urlopen(request, timeout=self._timeout):
            return

    def _key(self, cart_session_id: str) -> str:
        return f"{self._prefix}:{cart_session_id}"


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

        return _map_cart_snapshot(payload)

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
            payload.update(_normalize_item_meta_payload(item_meta))
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
        except HTTPError:
            current = self.get_cart(token)
            merged_items: list[tuple[str, int]] = []
            current_quantity = 0
            for item in current.items:
                if item.quantity <= 0:
                    continue
                merged_items.append((item.product_id, item.quantity))
                if item.product_id == product_id:
                    current_quantity = item.quantity
            next_quantity = max(0, current_quantity + quantity)
            merged_by_product_id: dict[str, int] = {item_id: item_qty for item_id, item_qty in merged_items}
            if next_quantity <= 0:
                merged_by_product_id.pop(product_id, None)
            else:
                merged_by_product_id[product_id] = next_quantity
            meta_payload: dict[str, dict[str, object]] = {}
            if item_meta:
                meta_payload[product_id] = _normalize_item_meta_payload(item_meta)
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
                row.update(_normalize_item_meta_payload(item_meta_by_product_id[product_id]))
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


def my_cart(
    *,
    cart_session_id: str | None = None,
    repository: CartApiRepository | None = None,
    token_store: CartTokenStore | None = None,
) -> dict[str, object]:
    """Tool entrypoint that returns cart snapshot for session."""

    service = _build_cart_service(repository=repository, token_store=token_store)
    return service.my_cart(normalize_cart_session_id(cart_session_id))


def add_to_my_cart(
    *,
    product_id: str | None = None,
    quantity: int | None = None,
    items: list[dict[str, object]] | None = None,
    cart_session_id: str | None = None,
    use_add_endpoint: bool = False,
    name: str | None = None,
    price: float | None = None,
    discount_price: float | None = None,
    manufacturer: str | None = None,
    repository: CartApiRepository | None = None,
    token_store: CartTokenStore | None = None,
) -> dict[str, object]:
    """Tool entrypoint that updates cart and returns current snapshot."""

    service = _build_cart_service(repository=repository, token_store=token_store)
    normalized_items: list[tuple[str, int]] | None = None
    item_meta_by_product_id: dict[str, dict[str, object]] | None = None
    if items:
        normalized_items = []
        item_meta_by_product_id = {}
        for raw_item in items:
            if not isinstance(raw_item, dict):
                raise ValueError("items must be an array of objects")
            raw_product_id = raw_item.get("product_id")
            raw_quantity = raw_item.get("quantity")
            normalized_product_id = str(raw_product_id or "").strip()
            if not normalized_product_id:
                raise ValueError("items product_id must not be empty")
            try:
                normalized_quantity = int(raw_quantity)
            except (TypeError, ValueError):
                raise ValueError("items quantity must be an integer") from None
            normalized_items.append((normalized_product_id, normalized_quantity))
            normalized_meta = _normalize_item_meta_payload(raw_item)
            if normalized_meta:
                item_meta_by_product_id[normalized_product_id] = normalized_meta
        if not item_meta_by_product_id:
            item_meta_by_product_id = None

    return service.add_to_cart(
        product_id=product_id,
        quantity=quantity,
        items=normalized_items,
        cart_session_id=normalize_cart_session_id(cart_session_id),
        use_add_endpoint=bool(use_add_endpoint),
        name=str(name) if isinstance(name, str) else None,
        price=float(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
        discount_price=(
            float(discount_price)
            if isinstance(discount_price, (int, float)) and not isinstance(discount_price, bool)
            else None
        ),
        manufacturer=str(manufacturer) if isinstance(manufacturer, str) else None,
        item_meta_by_product_id=item_meta_by_product_id,
    )


def _build_cart_service(
    *, repository: CartApiRepository | None, token_store: CartTokenStore | None
) -> CartService:
    return CartService(
        repository or AptekaCartRepository(),
        token_store or _build_default_token_store(),
    )


def _build_default_token_store() -> CartTokenStore:
    return _build_default_token_store_cached()


@lru_cache(maxsize=1)
def _build_default_token_store_cached() -> CartTokenStore:
    settings = get_settings()
    upstash_url = settings.upstash_redis_rest_url.strip()
    upstash_token = settings.upstash_redis_rest_token.strip()
    ttl_seconds = settings.cart_token_ttl_seconds
    if upstash_url and upstash_token:
        return UpstashRestCartTokenStore(
            base_url=upstash_url,
            token=upstash_token,
            ttl_seconds=ttl_seconds,
        )

    redis_url = settings.redis_url.strip()
    if not redis_url:
        return InMemoryCartTokenStore(ttl_seconds=ttl_seconds)

    try:
        import redis  # type: ignore
    except ImportError:
        return InMemoryCartTokenStore(ttl_seconds=ttl_seconds)

    client = redis.from_url(redis_url, decode_responses=False)
    return RedisCartTokenStore(client, ttl_seconds=ttl_seconds)


def _clear_default_token_store() -> None:
    _build_default_token_store_cached.cache_clear()


def _map_cart_snapshot(payload: Any) -> CartSnapshot:
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
            name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
            manufacturer = (
                raw_manufacturer.strip()
                if isinstance(raw_manufacturer, str) and raw_manufacturer.strip()
                else None
            )
            price: float | None = None
            discount_price: float | None = None
            if isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool):
                price = float(raw_price)
            if isinstance(raw_discount_price, (int, float)) and not isinstance(
                raw_discount_price, bool
            ):
                discount_price = float(raw_discount_price)
            items.append(
                CartItem(
                    product_id=product_id,
                    quantity=quantity,
                    name=name,
                    price=price,
                    discount_price=discount_price,
                    manufacturer=manufacturer,
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
    total: float | None
    if total_raw is None:
        total = None
    else:
        try:
            total = float(total_raw)
        except (TypeError, ValueError):
            total = None

    return CartSnapshot(items=items, count=count, total=total)


def _normalize_item_meta_payload(raw_payload: dict[str, object]) -> dict[str, object]:
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
    if isinstance(raw_price, (int, float)) and not isinstance(raw_price, bool):
        payload["price"] = float(raw_price)

    raw_discount_price = raw_payload.get("discount_price")
    if isinstance(raw_discount_price, (int, float)) and not isinstance(raw_discount_price, bool):
        payload["discount_price"] = float(raw_discount_price)

    return payload
