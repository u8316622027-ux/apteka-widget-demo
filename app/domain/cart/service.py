"""Cart business rules."""

from __future__ import annotations

from dataclasses import asdict
from typing import Callable
from uuid import uuid4

from app.domain.cart.entities import CartSnapshot, CartToken
from app.domain.cart.repository import CartApiRepository, CartTokenStore


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
        product_id: str,
        quantity: int | None = None,
        cart_session_id: str | None = None,
    ) -> dict[str, object]:
        normalized_product_id = product_id.strip()
        if not normalized_product_id:
            raise ValueError("product_id must not be empty")
        if quantity is not None and quantity < 0:
            raise ValueError("quantity must be greater than or equal to zero")

        session_id, token, created = self._ensure_session(cart_session_id)
        if quantity is None:
            snapshot = self._repository.add_item(token, product_id=normalized_product_id, quantity=1)
        else:
            snapshot = self._repository.update_item_quantity(
                token,
                product_id=normalized_product_id,
                quantity=quantity,
            )
        return self._response_payload(session_id, created, snapshot)

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
