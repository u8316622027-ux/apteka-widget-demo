"""MCP tool registry and serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import get_settings
from app.interfaces.mcp.tools.apteka_urls import get_apteka_base_url
from app.interfaces.mcp.tools.cart_tools import add_to_my_cart, my_cart
from app.interfaces.mcp.tools.checkout_tools import checkout_order
from app.interfaces.mcp.tools.faq_tools import faq_search
from app.interfaces.mcp.tools.search_tools import search_products
from app.interfaces.mcp.tools.tracking_tools import track_order_status_ui


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Metadata and callable for an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    output_template: str
    ui: dict[str, Any]


def create_tool_registry() -> dict[str, ToolDefinition]:
    """Create the default tool registry for MCP requests."""
    widget_ui_config = _build_widget_ui_config()

    return {
        "search_products": ToolDefinition(
            name="search_products",
            description=(
                "Search products by free-text query via Stage API. "
                "Args: query and optional limit. "
                "Returns structuredContent.products and structuredContent.no_results when empty."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
            },
            handler=_search_products_handler,
            output_template="ui://widget/products.html",
            ui=widget_ui_config,
        ),
        "add_to_my_cart": ToolDefinition(
            name="add_to_my_cart",
            description=(
                "Manage cart with two modes. "
                "Default mode uses /cart/update with full-state merge. "
                "For single card add UI, pass use_add_endpoint=true with product_id to use /cart/add. "
                "Batch update: pass items=[{product_id,quantity},...], "
                "where quantity is absolute target and 0 removes item."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "quantity": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Deprecated. For single product only; prefer items[].",
                    },
                    "name": {"type": "string"},
                    "price": {"type": "number"},
                    "discount_price": {"type": "number"},
                    "manufacturer": {"type": "string"},
                    "image_url": {"type": "string"},
                    "use_add_endpoint": {
                        "type": "boolean",
                        "description": "Optional UI-only flag for single-card add via /cart/add.",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 0},
                                "name": {"type": "string"},
                                "price": {"type": "number"},
                                "discount_price": {"type": "number"},
                                "manufacturer": {"type": "string"},
                                "image_url": {"type": "string"},
                            },
                            "required": ["product_id", "quantity"],
                        },
                    },
                    "cart_session_id": {"type": "string"},
                },
                "anyOf": [{"required": ["product_id"]}, {"required": ["items"]}],
            },
            handler=_add_to_my_cart_handler,
            output_template="ui://widget/products.html",
            ui=widget_ui_config,
        ),
        "checkout_order": ToolDefinition(
            name="checkout_order",
            description=(
                "Start checkout flow from current cart. "
                "If cart is empty, returns a friendly prompt to add products first. "
                "If cart has items, returns first step with delivery method options."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cart_session_id": {"type": "string"},
                    "delivery_method": {"type": "string", "enum": ["pickup", "courier_delivery"]},
                    "pickup_region_id": {"type": "integer", "minimum": 1},
                    "pickup_region_name": {"type": "string"},
                    "pickup_city_id": {"type": "integer", "minimum": 1},
                    "pickup_city_name": {"type": "string"},
                    "pickup_pharmacy_id": {"type": "integer", "minimum": 1},
                    "pickup_pharmacy_name": {"type": "string"},
                    "pickup_contact": {
                        "type": "object",
                        "properties": {
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "phone": {"type": "string"},
                            "email": {"type": "string"},
                        },
                    },
                    "courier_contact": {
                        "type": "object",
                        "properties": {
                            "first_name": {"type": "string"},
                            "last_name": {"type": "string"},
                            "phone": {"type": "string"},
                            "email": {"type": "string"},
                        },
                    },
                    "courier_address": {
                        "type": "object",
                        "properties": {
                            "region_id": {"type": "integer", "minimum": 1},
                            "region_name": {"type": "string"},
                            "city_id": {"type": "integer", "minimum": 1},
                            "city_name": {"type": "string"},
                            "street": {"type": "string"},
                            "house_number": {"type": "string"},
                            "apartment": {"type": "string"},
                            "entrance": {"type": "string"},
                            "floor": {"type": "string"},
                            "intercom_code": {"type": "string"},
                        },
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["card_on_receipt", "cash_on_receipt", "bank_transfer"],
                    },
                    "dont_call_me": {"type": "boolean"},
                    "terms_accepted": {"type": "boolean"},
                    "comment": {"type": "string"},
                },
            },
            handler=_checkout_order_handler,
            output_template="ui://widget/products.html",
            ui=widget_ui_config,
        ),
        "support_knowledge_search": ToolDefinition(
            name="support_knowledge_search",
            description=(
                "Semantic FAQ knowledge search for support questions: order placement, "
                "work schedule, app capabilities, payment, delivery, and account usage."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
            },
            handler=_support_knowledge_search_handler,
            output_template="",
            ui=widget_ui_config,
        ),
        "my_cart": ToolDefinition(
            name="my_cart",
            description="Get current user cart state.",
            input_schema={
                "type": "object",
                "properties": {"cart_session_id": {"type": "string"}},
            },
            handler=_my_cart_handler,
            output_template="ui://widget/my-cart.html",
            ui=widget_ui_config,
        ),
        "set_widget_theme": ToolDefinition(
            name="set_widget_theme",
            description="Set storefront widget theme.",
            input_schema={"type": "object"},
            handler=_not_implemented_tool("set_widget_theme"),
            output_template="",
            ui=widget_ui_config,
        ),
        "track_order_status_ui": ToolDefinition(
            name="track_order_status_ui",
            description=(
                "Track order status by order number or phone. "
                "For phone input, use full international format with country code first. "
                "If the order was just created and user searches by order number, "
                "tracking by number becomes available only after operator accepts the order, "
                "so advise user to wait a bit and try again. "
                "Use returned status_hint to explain context to user. "
                "Do not treat packed as ready for pickup until client_notified."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "lookup": {"type": "string"},
                },
                "required": ["lookup"],
            },
            handler=_track_order_status_ui_handler,
            output_template="ui://widget/products.html",
            ui=widget_ui_config,
        ),
    }


def serialize_tool_definition(tool: ToolDefinition) -> dict[str, Any]:
    payload = {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
        "ui": tool.ui,
        "_meta": {
            "openai/widgetAccessible": True,
            "openai/widgetDomain": str(tool.ui.get("domain") or ""),
            "openai/widgetCSP": tool.ui.get("csp") or {},
        },
    }
    if tool.output_template:
        payload["outputTemplate"] = tool.output_template
        payload["_meta"]["openai/outputTemplate"] = tool.output_template
    return payload


def decorate_tool_result(
    tool_name: str, tool: ToolDefinition, result_payload: dict[str, Any]
) -> dict[str, Any]:
    payload = dict(result_payload)

    if tool_name == "search_products":
        products = payload.get("products")
        if isinstance(products, list):
            normalized_products = products
        else:
            normalized_products = []
        payload["products"] = normalized_products
        payload["no_results"] = len(normalized_products) == 0

    if tool.output_template:
        payload["widget"] = {
            "open": {
                "template": tool.output_template,
                "replace_previous": True,
                "page": _resolve_widget_page(tool_name),
            },
            "ui": tool.ui,
        }
    return payload


def _resolve_widget_page(tool_name: str) -> str:
    if tool_name == "search_products":
        return "search"
    if tool_name in {"my_cart", "add_to_my_cart"}:
        return "my-cart"
    if tool_name == "checkout_order":
        return "checkout"
    if tool_name == "track_order_status_ui":
        return "tracking"
    return "search"


def _build_widget_ui_config() -> dict[str, Any]:
    settings = get_settings()
    widget_domain = (
        str(
            getattr(
                settings,
                "mcp_widget_domain",
                "https://subgerminal-yevette-lactogenic.ngrok-free.dev",
            )
        ).strip()
        or "https://subgerminal-yevette-lactogenic.ngrok-free.dev"
    )
    apteka_base_url = get_apteka_base_url()
    resource_domains = [
        widget_domain,
        apteka_base_url,
        "https://www.apteka.md",
        "https://cdn.jsdelivr.net",
    ]
    return {
        "domain": widget_domain,
        "csp": {
            "connectDomains": [apteka_base_url],
            "resourceDomains": resource_domains,
        },
    }


def _not_implemented_tool(tool_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "not_implemented",
            "tool": tool_name,
            "arguments": arguments,
        }

    return _handler


def _search_products_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", ""))
    limit = int(arguments.get("limit", 10))
    return search_products(query, limit=limit)


def _my_cart_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    cart_session_id = arguments.get("cart_session_id")
    return my_cart(cart_session_id=str(cart_session_id) if cart_session_id is not None else None)


def _add_to_my_cart_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    product_id_value = arguments.get("product_id")
    product_id = str(product_id_value) if product_id_value is not None else None
    quantity_value = arguments.get("quantity")
    quantity = int(quantity_value) if quantity_value is not None else None
    items_value = arguments.get("items")
    items = items_value if isinstance(items_value, list) else None
    cart_session_id = arguments.get("cart_session_id")
    name = arguments.get("name")
    price = arguments.get("price")
    discount_price = arguments.get("discount_price")
    manufacturer = arguments.get("manufacturer")
    image_url = arguments.get("image_url")
    use_add_endpoint = bool(arguments.get("use_add_endpoint")) if isinstance(
        arguments.get("use_add_endpoint"), bool
    ) else False
    return add_to_my_cart(
        product_id=product_id,
        quantity=quantity,
        items=items,
        cart_session_id=str(cart_session_id) if cart_session_id is not None else None,
        use_add_endpoint=use_add_endpoint,
        name=str(name) if isinstance(name, str) else None,
        price=float(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
        discount_price=(
            float(discount_price)
            if isinstance(discount_price, (int, float)) and not isinstance(discount_price, bool)
            else None
        ),
        manufacturer=str(manufacturer) if isinstance(manufacturer, str) else None,
        image_url=str(image_url) if isinstance(image_url, str) else None,
    )


def _track_order_status_ui_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    lookup = str(arguments.get("lookup", ""))
    return track_order_status_ui(lookup)


def _support_knowledge_search_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", ""))
    limit_value = arguments.get("limit")
    limit = int(limit_value) if limit_value is not None else None
    return faq_search(query, limit=limit)


def _checkout_order_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    cart_session_id = arguments.get("cart_session_id")
    delivery_method = arguments.get("delivery_method")
    pickup_region_id = arguments.get("pickup_region_id")
    pickup_region_name = arguments.get("pickup_region_name")
    pickup_city_id = arguments.get("pickup_city_id")
    pickup_city_name = arguments.get("pickup_city_name")
    pickup_pharmacy_id = arguments.get("pickup_pharmacy_id")
    pickup_pharmacy_name = arguments.get("pickup_pharmacy_name")
    pickup_contact = arguments.get("pickup_contact")
    courier_contact = arguments.get("courier_contact")
    courier_address = arguments.get("courier_address")
    payment_method = arguments.get("payment_method")
    dont_call_me = arguments.get("dont_call_me")
    terms_accepted = arguments.get("terms_accepted")
    comment = arguments.get("comment")
    return checkout_order(
        cart_session_id=str(cart_session_id) if cart_session_id is not None else None,
        delivery_method=str(delivery_method) if delivery_method is not None else None,
        pickup_region_id=pickup_region_id,
        pickup_region_name=str(pickup_region_name) if pickup_region_name is not None else None,
        pickup_city_id=pickup_city_id,
        pickup_city_name=str(pickup_city_name) if pickup_city_name is not None else None,
        pickup_pharmacy_id=pickup_pharmacy_id,
        pickup_pharmacy_name=str(pickup_pharmacy_name) if pickup_pharmacy_name is not None else None,
        pickup_contact=pickup_contact if isinstance(pickup_contact, dict) else None,
        courier_contact=courier_contact if isinstance(courier_contact, dict) else None,
        courier_address=courier_address if isinstance(courier_address, dict) else None,
        payment_method=str(payment_method) if payment_method is not None else None,
        dont_call_me=bool(dont_call_me) if isinstance(dont_call_me, bool) else None,
        terms_accepted=bool(terms_accepted) if isinstance(terms_accepted, bool) else None,
        comment=str(comment) if comment is not None else None,
    )
