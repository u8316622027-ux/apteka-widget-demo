"""Cart business rules."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import threading
from typing import Callable
from uuid import uuid4

from app.domain.cart.entities import CartSnapshot, CartToken
from app.domain.cart.repository import CartApiRepository, CartTokenStore

_SESSION_LOCK_GUARD = threading.Lock()
_SESSION_LOCKS: dict[str, threading.Lock] = {}


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
    ) -> dict[str, object]:
        session_id, token, created = self._ensure_session(cart_session_id)

        if items:
            normalized_updates = self._normalize_items(items)
            with _session_update_lock(session_id):
                snapshot = self._update_cart_with_merge(token, normalized_updates)
            return self._response_payload(session_id, created, snapshot)

        normalized_product_id = (product_id or "").strip()
        if not normalized_product_id:
            raise ValueError("product_id must not be empty")
        if quantity is not None and quantity < 0:
            raise ValueError("quantity must be greater than or equal to zero")

        # Single-item add path always uses /cart/add semantics.
        add_quantity = 1 if quantity is None else quantity
        if add_quantity == 0:
            with _session_update_lock(session_id):
                snapshot = self._update_cart_with_merge(token, [(normalized_product_id, 0)])
        else:
            snapshot = self._repository.add_item(
                token,
                product_id=normalized_product_id,
                quantity=add_quantity,
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
    ) -> CartSnapshot:
        current = self._repository.get_cart(token)
        merged: dict[str, int] = {item.product_id: item.quantity for item in current.items}
        for product_id, quantity in updates:
            if quantity == 0:
                merged.pop(product_id, None)
                continue
            merged[product_id] = quantity

        merged_items = list(merged.items())
        return self._repository.update_items(token, items=merged_items)

    def _ensure_session(self, cart_session_id: str | None) -> tuple[str, CartToken, bool]:
        normalized_session_id = (cart_session_id or "").strip()
        if normalized_session_id:
            token = self._token_store.get_token(normalized_session_id)
            if token is not None:
                return normalized_session_id, token, False

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
        lock = _SESSION_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _SESSION_LOCKS[session_id] = lock

    lock.acquire()
    try:
        yield
    finally:
        lock.release()
