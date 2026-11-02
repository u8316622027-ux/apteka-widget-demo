"""Cart repository contracts."""

from __future__ import annotations

from typing import Protocol

from app.domain.cart.entities import CartSnapshot, CartToken


class CartApiRepository(Protocol):
    """Abstraction for cart API operations."""

    def create_cart(self) -> CartToken:
        """Create cart and return auth token."""

    def get_cart(self, token: CartToken) -> CartSnapshot:
        """Fetch current cart snapshot for token."""

    def add_item(
        self,
        token: CartToken,
        *,
        product_id: str,
        quantity: int,
        item_meta: dict[str, object] | None = None,
    ) -> CartSnapshot:
        """Increment item quantity in cart and return updated snapshot."""

    def update_items(
        self,
        token: CartToken,
        *,
        items: list[tuple[str, int]],
        item_meta_by_product_id: dict[str, dict[str, object]] | None = None,
    ) -> CartSnapshot:
        """Apply absolute quantities for provided items and return updated snapshot."""


class CartTokenStore(Protocol):
    """Persistence abstraction for cart session -> token mapping."""

    def get_token(self, cart_session_id: str) -> CartToken | None:
        """Return token for a session id if it exists."""

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        """Persist token for a session id."""
