"""MCP cart tools."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from time import time
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen as default_urlopen

from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.domain.cart.repository import CartApiRepository, CartTokenStore
from app.domain.cart.service import CartService
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id

APTEKA_CART_URL = "https://api.apteka.md/api/v1/front/cart"
_DEFAULT_TOKEN_STORE: CartTokenStore | None = None


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
        base_url: str = APTEKA_CART_URL,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = base_url.rstrip("/")
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

    def add_item(self, token: CartToken, *, product_id: str, quantity: int) -> CartSnapshot:
        for _ in range(quantity):
            request_payload = json.dumps(
                {"id": product_id},
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
            with self._urlopen(request, timeout=self._timeout):
                continue

        return self.get_cart(token)

    def update_item_quantity(
        self, token: CartToken, *, product_id: str, quantity: int
    ) -> CartSnapshot:
        request_payload = json.dumps(
            {"items": [{"product_id": product_id, "quantity": quantity}], "json": True},
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
    product_id: str,
    quantity: int | None = None,
    cart_session_id: str | None = None,
    repository: CartApiRepository | None = None,
    token_store: CartTokenStore | None = None,
) -> dict[str, object]:
    """Tool entrypoint that updates cart and returns current snapshot."""

    service = _build_cart_service(repository=repository, token_store=token_store)
    return service.add_to_cart(
        product_id=product_id,
        quantity=quantity,
        cart_session_id=normalize_cart_session_id(cart_session_id),
    )


def _build_cart_service(
    *, repository: CartApiRepository | None, token_store: CartTokenStore | None
) -> CartService:
    return CartService(
        repository or AptekaCartRepository(),
        token_store or _build_default_token_store(),
    )


def _build_default_token_store() -> CartTokenStore:
    global _DEFAULT_TOKEN_STORE
    if _DEFAULT_TOKEN_STORE is not None:
        return _DEFAULT_TOKEN_STORE

    upstash_url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
    upstash_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    ttl_seconds = _get_cart_ttl_seconds()
    if upstash_url and upstash_token:
        _DEFAULT_TOKEN_STORE = UpstashRestCartTokenStore(
            base_url=upstash_url,
            token=upstash_token,
            ttl_seconds=ttl_seconds,
        )
        return _DEFAULT_TOKEN_STORE

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        _DEFAULT_TOKEN_STORE = InMemoryCartTokenStore(ttl_seconds=ttl_seconds)
        return _DEFAULT_TOKEN_STORE

    try:
        import redis  # type: ignore
    except ImportError:
        _DEFAULT_TOKEN_STORE = InMemoryCartTokenStore(ttl_seconds=ttl_seconds)
        return _DEFAULT_TOKEN_STORE

    client = redis.from_url(redis_url, decode_responses=False)
    _DEFAULT_TOKEN_STORE = RedisCartTokenStore(client, ttl_seconds=ttl_seconds)
    return _DEFAULT_TOKEN_STORE


def _clear_default_token_store() -> None:
    global _DEFAULT_TOKEN_STORE
    _DEFAULT_TOKEN_STORE = None


def _get_cart_ttl_seconds(default: int = 604800) -> int:
    raw_value = os.environ.get("CART_TOKEN_TTL_SECONDS", "").strip()
    if not raw_value:
        return default

    try:
        ttl = int(raw_value)
    except ValueError:
        return default

    return ttl if ttl > 0 else default


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
            items.append(CartItem(product_id=product_id, quantity=quantity))

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
