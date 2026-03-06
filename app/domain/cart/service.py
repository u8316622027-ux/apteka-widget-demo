"""Cart business rules."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from dataclasses import dataclass
import threading
from typing import Callable
from uuid import uuid4

from app.domain.cart.entities import CartSnapshot, CartToken
from app.domain.cart.repository import CartApiRepository, CartTokenStore

_SESSION_LOCK_GUARD = threading.Lock()


@dataclass(slots=True)
class _SessionLockState:
    lock: threading.Lock
    users: int = 0


_SESSION_LOCKS: dict[str, _SessionLockState] = {}


class CartService:
    """Orchestrates cart session resolution and cart actions."""

    def __init__(
        self,
        repository: CartApiRepository,
        token_store: CartTokenStore,
        *,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._token_store = token_store
        self._session_id_factory = session_id_factory or (lambda: uuid4().hex)

    def my_cart(self, cart_session_id: str | None = None) -> dict[str, object]:
        session_id, token, created = self._ensure_session(cart_session_id)
        snapshot = self._repository.get_cart(token)
        return self._response_payload(session_id, created, snapshot)

    def add_to_cart(
        self,
        *,
        product_id: str | None = None,
        quantity: int | None = None,
        items: list[tuple[str, int]] | None = None,
        cart_session_id: str | None = None,
        use_add_endpoint: bool = False,
        name: str | None = None,
        price: float | None = None,
        discount_price: float | None = None,
        manufacturer: str | None = None,
        item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
    ) -> dict[str, object]:
        session_id, token, created = self._ensure_session(cart_session_id)

        if items:
            normalized_updates = self._normalize_items(items)
            with _session_update_lock(session_id):
                snapshot = self._update_cart_with_merge(
                    token,
                    normalized_updates,
                    item_meta_by_product_id=item_meta_by_product_id,
                )
            return self._response_payload(session_id, created, snapshot)

        normalized_product_id = (product_id or "").strip()
        if not normalized_product_id:
            raise ValueError("product_id must not be empty")
        if quantity is not None and quantity < 0:
            raise ValueError("quantity must be greater than or equal to zero")

        # Single-item default path uses update semantics with full-state merge.
        # Explicit add endpoint is used only for UI single-card add.
        add_quantity = 1 if quantity is None else quantity
        if add_quantity == 0:
            with _session_update_lock(session_id):
                snapshot = self._update_cart_with_merge(
                    token,
                    [(normalized_product_id, 0)],
                    item_meta_by_product_id=item_meta_by_product_id,
                )
        elif use_add_endpoint:
            item_meta = self._build_item_meta(
                name=name,
                price=price,
                discount_price=discount_price,
                manufacturer=manufacturer,
            )
            snapshot = self._repository.add_item(
                token,
                product_id=normalized_product_id,
                quantity=add_quantity,
                item_meta=item_meta,
            )
        else:
            item_meta = self._build_item_meta(
                name=name,
                price=price,
                discount_price=discount_price,
                manufacturer=manufacturer,
            )
            next_meta_by_product_id = dict(item_meta_by_product_id or {})
            if item_meta:
                next_meta_by_product_id[normalized_product_id] = item_meta
            with _session_update_lock(session_id):
                current_snapshot = self._repository.get_cart(token)
                current_quantity = 0
                for item in current_snapshot.items:
                    if item.product_id == normalized_product_id:
                        current_quantity = max(0, item.quantity)
                        break
                next_quantity = max(0, current_quantity + add_quantity)
                snapshot = self._update_cart_with_merge(
                    token,
                    [(normalized_product_id, next_quantity)],
                    item_meta_by_product_id=next_meta_by_product_id or None,
                    current_snapshot=current_snapshot,
                )
        return self._response_payload(session_id, created, snapshot)

    def _normalize_items(self, items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        collapsed: dict[str, int] = {}
        for product_id, quantity in items:
            normalized_product_id = str(product_id).strip()
            if not normalized_product_id:
                raise ValueError("items product_id must not be empty")
            if quantity < 0:
                raise ValueError("items quantity must be greater than or equal to zero")
            if normalized_product_id in collapsed:
                collapsed.pop(normalized_product_id)
            collapsed[normalized_product_id] = quantity
        return list(collapsed.items())

    def _update_cart_with_merge(
        self,
        token: CartToken,
        updates: list[tuple[str, int]],
        *,
        item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
        current_snapshot: CartSnapshot | None = None,
    ) -> CartSnapshot:
        current = current_snapshot or self._repository.get_cart(token)
        merged_quantities: dict[str, int] = {}
        merged_item_meta_by_product_id: dict[str, dict[str, object]] = {}

        for item in current.items:
            if item.quantity <= 0:
                continue
            merged_quantities[item.product_id] = item.quantity
            meta: dict[str, object] = {}
            if item.name is not None:
                meta["name"] = item.name
            if item.manufacturer is not None:
                meta["manufacturer"] = item.manufacturer
            if item.price is not None:
                meta["price"] = float(item.price)
            if item.discount_price is not None:
                meta["discount_price"] = float(item.discount_price)
            if meta:
                merged_item_meta_by_product_id[item.product_id] = meta

        for product_id, quantity in updates:
            if quantity <= 0:
                merged_quantities.pop(product_id, None)
            else:
                merged_quantities[product_id] = quantity

        if item_meta_by_product_id:
            for product_id, raw_meta in item_meta_by_product_id.items():
                if product_id not in merged_quantities:
                    continue
                cleaned_meta: dict[str, object] = {}
                for key in ("name", "manufacturer", "price", "discount_price"):
                    value = raw_meta.get(key)
                    if value is None:
                        continue
                    cleaned_meta[key] = value
                if cleaned_meta:
                    previous_meta = merged_item_meta_by_product_id.get(product_id, {})
                    merged_item_meta_by_product_id[product_id] = {
                        **previous_meta,
                        **cleaned_meta,
                    }

        merged_items = list(merged_quantities.items())
        merged_meta_payload = {
            product_id: meta
            for product_id, meta in merged_item_meta_by_product_id.items()
            if product_id in merged_quantities
        }
        return self._repository.update_items(
            token,
            items=merged_items,
            item_meta_by_product_id=merged_meta_payload or None,
        )

    def _build_item_meta(
        self,
        *,
        name: str | None,
        price: float | None,
        discount_price: float | None,
        manufacturer: str | None,
    ) -> dict[str, object] | None:
        payload: dict[str, object] = {}
        normalized_name = (name or "").strip()
        normalized_manufacturer = (manufacturer or "").strip()
        if normalized_name:
            payload["name"] = normalized_name
        if normalized_manufacturer:
            payload["manufacturer"] = normalized_manufacturer
        if price is not None:
            payload["price"] = float(price)
        if discount_price is not None:
            payload["discount_price"] = float(discount_price)
        if not payload:
            return None
        return payload

    def _ensure_session(self, cart_session_id: str | None) -> tuple[str, CartToken, bool]:
        normalized_session_id = (cart_session_id or "").strip()
        if normalized_session_id:
            token = self._token_store.get_token(normalized_session_id)
            if token is not None:
                return normalized_session_id, token, False
            token = self._repository.create_cart()
            self._token_store.set_token(normalized_session_id, token)
            return normalized_session_id, token, True

        token = self._repository.create_cart()
        created_session_id = self._session_id_factory()
        self._token_store.set_token(created_session_id, token)
        return created_session_id, token, True

    def _response_payload(
        self,
        session_id: str,
        created: bool,
        snapshot: CartSnapshot,
    ) -> dict[str, object]:
        return {
            "cart_session_id": session_id,
            "cart_created": created,
            "count": snapshot.count,
            "total": snapshot.total,
            "items": [asdict(item) for item in snapshot.items],
        }


@contextmanager
def _session_update_lock(session_id: str):
    with _SESSION_LOCK_GUARD:
        state = _SESSION_LOCKS.get(session_id)
        if state is None:
            state = _SessionLockState(lock=threading.Lock())
            _SESSION_LOCKS[session_id] = state
        state.users += 1

    state.lock.acquire()
    try:
        yield
    finally:
        state.lock.release()
        with _SESSION_LOCK_GUARD:
            current = _SESSION_LOCKS.get(session_id)
            if current is state:
                current.users -= 1
                if current.users <= 0:
                    _SESSION_LOCKS.pop(session_id, None)
