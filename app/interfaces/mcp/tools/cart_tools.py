"""MCP cart tools facade."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.domain.cart.repository import CartApiRepository, CartTokenStore
from app.domain.cart.service import CartService
from app.interfaces.mcp.tools.cart import (
    APTEKA_CART_PATH,
    AptekaCartRepository,
    InMemoryCartTokenStore,
    RedisCartTokenStore,
    UpstashRestCartTokenStore,
    coerce_money,
    map_cart_snapshot,
    money_to_wire,
    normalize_item_meta_payload,
)
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id

__all__ = [
    "APTEKA_CART_PATH",
    "AptekaCartRepository",
    "InMemoryCartTokenStore",
    "RedisCartTokenStore",
    "UpstashRestCartTokenStore",
    "add_to_my_cart",
    "my_cart",
    "_build_default_token_store",
    "_clear_default_token_store",
]


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
    price: Any = None,
    discount_price: Any = None,
    manufacturer: str | None = None,
    image_url: str | None = None,
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
            normalized_meta = normalize_item_meta_payload(raw_item)
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
        price=coerce_money(price),
        discount_price=coerce_money(discount_price),
        manufacturer=str(manufacturer) if isinstance(manufacturer, str) else None,
        image_url=str(image_url) if isinstance(image_url, str) else None,
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


# Re-exported internals for backward compatibility in tests.
_map_cart_snapshot = map_cart_snapshot
_normalize_item_meta_payload = normalize_item_meta_payload
_coerce_money = coerce_money
_money_to_wire = money_to_wire
