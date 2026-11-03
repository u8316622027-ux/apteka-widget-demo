"""Single-purpose MCP actions over the existing isolated Apteka cart and checkout."""

from __future__ import annotations

from app.interfaces.mcp.tools.cart_tools import _build_cart_service, add_to_my_cart, my_cart
from app.interfaces.mcp.tools.checkout_tools import checkout_order
from app.interfaces.mcp.tools.search_tools import search_products
from app.interfaces.mcp.tools.shared_context import normalize_cart_session_id


def _service(repository=None, token_store=None):
    return _build_cart_service(repository=repository, token_store=token_store)


def _quantity(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"quantity must be an integer greater than or equal to {minimum}")
    return value


def _product_id(value):
    value = str(value or "").strip()
    if not value:
        raise ValueError("product_id is required")
    return value


def check_cart(arguments, *, repository=None, token_store=None):
    return _service(repository, token_store).check_cart(
        normalize_cart_session_id(arguments.get("cart_session_id"))
    )


def sync_cart(arguments, *, repository=None, token_store=None):
    """Ensure a backend session; never overwrite it with browser-supplied prices/items."""
    return my_cart(
        cart_session_id=normalize_cart_session_id(arguments.get("cart_session_id")),
        repository=repository,
        token_store=token_store,
    )


def add_to_cart(arguments, *, repository=None, token_store=None):
    product_id = _product_id(arguments.get("product_id"))
    quantity = _quantity(arguments.get("quantity", 1), 1)
    return add_to_my_cart(
        product_id=product_id,
        quantity=quantity,
        cart_session_id=normalize_cart_session_id(arguments.get("cart_session_id")),
        repository=repository,
        token_store=token_store,
    )


def update_cart_item(arguments, *, repository=None, token_store=None):
    product_id = _product_id(arguments.get("product_id"))
    quantity = _quantity(arguments.get("quantity"))
    session_id = normalize_cart_session_id(arguments.get("cart_session_id"))
    if not session_id:
        raise ValueError("cart_session_id is required; check the cart first")
    return _service(repository, token_store).update_cart_item(session_id, product_id, quantity)


def clear_cart(arguments, *, repository=None, token_store=None):
    return _service(repository, token_store).clear_cart(
        normalize_cart_session_id(arguments.get("cart_session_id"))
    )


def search_and_add_to_cart(arguments, *, repository=None, token_store=None, searcher=None):
    """Search and add an explicitly selected or unique priced result."""
    quantity = _quantity(arguments.get("quantity", 1), 1)
    found = (searcher or search_products)(
        arguments.get("query", ""), language=arguments.get("language")
    )
    if found.get("upstream_error"):
        return {**found, "status": "search_unavailable", "no_results": False}
    products = found.get("products") or []
    if not products:
        return {**found, "status": "no_results", "no_results": True}
    product_id = str(arguments.get("product_id") or "").strip()
    index = arguments.get("product_index")
    selected = None
    if index is not None:
        if type(index) is not int or index < 1 or index > len(products):
            raise ValueError("product_index must identify a returned search result")
        selected = products[index - 1]
        if product_id and str(selected.get("id")) != product_id:
            raise ValueError("product_id and product_index identify different products")
    elif product_id:
        selected = next((item for item in products if str(item.get("id")) == product_id), None)
        if selected is None:
            raise ValueError("product_id is not in these search results")
    elif len(products) == 1:
        selected = products[0]
    if selected is None:
        return {**found, "status": "selection_required", "no_results": False}
    if not isinstance(selected.get("price"), (int, float)) or selected["price"] <= 0:
        raise ValueError("Choose an available product with a positive price")
    cart = add_to_cart(
        {
            "cart_session_id": arguments.get("cart_session_id"),
            "product_id": str(selected["id"]),
            "quantity": quantity,
        },
        repository=repository,
        token_store=token_store,
    )
    return {**cart, "status": "cart_updated", "language": found.get("language", "ru")}


def _checkout(action, arguments, **dependencies):
    if "action" in arguments:
        raise ValueError("action cannot override a single-purpose checkout tool")
    return checkout_order({**arguments, "action": action}, **dependencies)


def get_checkout_options(arguments, **dependencies):
    return _checkout("options", arguments, **dependencies)


def get_delivery_windows(arguments, **dependencies):
    return _checkout("delivery", arguments, **dependencies)


def review_order(arguments, **dependencies):
    return _checkout("review", arguments, **dependencies)


def submit_order(arguments, **dependencies):
    return _checkout("submit", arguments, **dependencies)


def open_checkout(arguments):
    """Navigate only; loading the cart/options is handled by distinct widget calls."""
    return {
        "status": "ok",
        "action": "open_checkout",
        "widget_page": "checkout",
        "checkout_step": "delivery",
        **arguments,
    }


def set_widget_theme(arguments):
    theme = arguments.get("theme")
    if theme not in {"light", "dark", "auto"}:
        raise ValueError("theme must be light, dark, or auto")
    return {
        "status": "ok",
        "action": "set_widget_theme",
        **arguments,
        "theme_mode": "auto" if theme == "auto" else "manual",
        "auto_disabled": theme != "auto",
    }


def set_widget_language(arguments):
    if arguments.get("language") not in {"ru", "ro"}:
        raise ValueError("language must be ru or ro")
    return {"status": "ok", "action": "set_widget_language", **arguments}
