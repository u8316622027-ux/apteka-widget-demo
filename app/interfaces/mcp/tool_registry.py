"""MCP tool registry and serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import get_settings
from app.interfaces.mcp.tools.apteka_urls import get_apteka_base_url, get_apteka_media_base_url
from app.interfaces.mcp.tools.cart_tools import add_to_my_cart, my_cart
from app.interfaces.mcp.tools.checkout_tools import checkout_order
from app.interfaces.mcp.tools.faq_tools import faq_search
from app.interfaces.mcp.tools.search_tools import search_products

# Change this version when the widget bundle changes to invalidate host UI caches.
PRODUCTS_WIDGET_TEMPLATE = "ui://widget/products.html?v=kokiko-2"


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Metadata and callable for an MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    output_template: str
    ui: dict[str, Any]
    title: str | None = None
    annotations: dict[str, Any] = field(default_factory=dict)
    tool_invocation: dict[str, str] = field(default_factory=dict)
    visibility: str = "public"


def create_tool_registry() -> dict[str, ToolDefinition]:
    """Create the default tool registry for MCP requests."""
    widget_ui_config = _build_widget_ui_config()

    registry = {
        "search_products": ToolDefinition(
            name="search_products",
            title="Search products",
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
                    "language": {
                        "type": "string",
                        "description": "User language preference (ru or ro).",
                    },
                },
                "required": ["query"],
            },
            handler=_search_products_handler,
            output_template=PRODUCTS_WIDGET_TEMPLATE,
            ui=widget_ui_config,
            annotations={
                "readOnlyHint": True,
                "openWorldHint": True,
                "destructiveHint": False,
            },
            tool_invocation={
                "invoking": "Searching products…",
                "invoked": "Products found.",
            },
        ),
        "support_knowledge_search": ToolDefinition(
            name="support_knowledge_search",
            title="Search support knowledge",
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
            annotations={
                "readOnlyHint": True,
                "openWorldHint": False,
                "destructiveHint": False,
            },
            tool_invocation={
                "invoking": "Searching support knowledge…",
                "invoked": "Support knowledge found.",
            },
        ),
    }
    registry.update(_commerce_tools(widget_ui_config))
    return registry


def _commerce_tools(ui):
    session = {
        "type": "string",
        "description": "Reuse the user's cart_session_id from prior results.",
    }
    language = {"type": "string", "enum": ["ru", "ro"]}
    definitions = [
        (
            "my_cart",
            "My cart",
            "Show the current user's cart. Always reuse cart_session_id when available.",
            {"cart_session_id": session},
            [],
            lambda args: my_cart(**args),
            True,
            False,
        ),
        (
            "add_to_my_cart",
            "Update my cart",
            "Add one product by product_id (quantity is an increment). "
            "For changes or removal use items with absolute quantities; zero removes an item. "
            "This can overwrite quantities or delete cart line items without an automatic undo. "
            "It changes the cart only; it does not place an order or charge a payment. "
            "Always reuse cart_session_id. Product prices come from Apteka API.",
            {
                "cart_session_id": session,
                "product_id": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 0},
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_id": {"type": "string"},
                            "quantity": {"type": "integer", "minimum": 0},
                        },
                        "required": ["product_id", "quantity"],
                        "additionalProperties": False,
                    },
                },
            },
            [],
            lambda args: add_to_my_cart(**args),
            False,
            True,
        ),
        (
            "checkout_order",
            "Checkout order",
            "Checkout the existing cart. options returns delivery choices; delivery returns "
            "available delivery windows. review validates contact, destination and payment "
            "and returns confirmation_id plus totals. submit sends contact and delivery details "
            "to Apteka and creates a real order; this tool cannot cancel that order. "
            "Payment is cash or card on receipt; this tool does not collect payment card details. "
            "Only call submit after the user explicitly approves that exact review and accepts "
            "the terms; pass confirmation_id and terms_accepted=true. Never invent contact "
            "details or retry an uncertain submission. Reuse cart_session_id.",
            {
                "cart_session_id": session,
                "language": language,
                "action": {"type": "string", "enum": ["options", "delivery", "review", "submit"]},
                "delivery_method": {"type": "string", "enum": ["pickup", "courier"]},
                "pharmacy_id": {"type": "integer", "minimum": 1},
                "region_id": {"type": "integer", "minimum": 1},
                "city_id": {"type": "integer", "minimum": 1},
                "contact": {
                    "type": "object",
                    "properties": {
                        key: {"type": "string"}
                        for key in ["first_name", "last_name", "phone", "email"]
                    },
                    "required": ["first_name", "phone"],
                    "additionalProperties": False,
                },
                "address": {
                    "type": "object",
                    "properties": {
                        key: {"type": "string"}
                        for key in [
                            "street",
                            "house_number",
                            "apartment",
                            "entrance",
                            "floor",
                            "intercom_code",
                        ]
                    },
                    "required": ["street", "house_number"],
                    "additionalProperties": False,
                },
                "delivery_window": {
                    "type": "object",
                    "properties": {
                        key: {"type": "string"} for key in ["deliveryDate", "from", "to"]
                    },
                    "required": ["deliveryDate", "from", "to"],
                    "additionalProperties": False,
                },
                "payment_method": {
                    "type": "string",
                    "enum": ["cash_on_receipt", "card_on_receipt"],
                },
                "comment": {"type": "string"},
                "dont_call_me": {"type": "boolean"},
                "terms_accepted": {"type": "boolean"},
                "confirmation_id": {"type": "string"},
            },
            ["cart_session_id"],
            checkout_order,
            False,
            True,
        ),
    ]
    return {
        name: ToolDefinition(
            name=name,
            title=title,
            description=description,
            input_schema={
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            handler=handler,
            output_template=PRODUCTS_WIDGET_TEMPLATE,
            ui=ui,
            annotations={
                "readOnlyHint": readonly,
                "openWorldHint": True,
                "destructiveHint": destructive,
            },
            tool_invocation={"invoking": "Loading…", "invoked": "Done."},
        )
        for (
            name,
            title,
            description,
            properties,
            required,
            handler,
            readonly,
            destructive,
        ) in definitions
    }


def serialize_tool_definition(tool: ToolDefinition) -> dict[str, Any]:
    ui_domain = str(tool.ui.get("domain") or "").strip()
    ui_csp = tool.ui.get("csp") if isinstance(tool.ui.get("csp"), dict) else {}
    connect_domains = ui_csp.get("connectDomains")
    resource_domains = ui_csp.get("resourceDomains")
    if not isinstance(connect_domains, list):
        connect_domains = []
    if not isinstance(resource_domains, list):
        resource_domains = []
    payload = {
        "name": tool.name,
        "title": tool.title or tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
        "ui": tool.ui,
        "_meta": {
            "ui": {"visibility": ["model", "app"]},
            "openai/widgetAccessible": True,
            "openai/widgetDomain": ui_domain,
            "openai/widgetCSP": {
                "connect_domains": list(connect_domains),
                "resource_domains": list(resource_domains),
            },
        },
    }
    if tool.tool_invocation:
        if tool.tool_invocation.get("invoking"):
            payload["_meta"]["openai/toolInvocation/invoking"] = tool.tool_invocation["invoking"]
        if tool.tool_invocation.get("invoked"):
            payload["_meta"]["openai/toolInvocation/invoked"] = tool.tool_invocation["invoked"]
    if tool.output_template:
        payload["_meta"]["ui"]["resourceUri"] = tool.output_template
        payload["outputTemplate"] = tool.output_template
        payload["_meta"]["openai/outputTemplate"] = tool.output_template
    if tool.annotations:
        payload["annotations"] = dict(tool.annotations)
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
    if tool_name in {"my_cart", "add_to_my_cart"}:
        return "cart"
    if tool_name == "checkout_order":
        return "checkout"
    if tool_name == "search_products":
        return "search"
    if tool_name == "support_knowledge_search":
        return "support"
    return "default"


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
        get_apteka_media_base_url(),
        "https://www.apteka.md",
    ]
    return {
        "domain": widget_domain,
        "csp": {
            "connectDomains": [apteka_base_url],
            "resourceDomains": list(dict.fromkeys(resource_domains)),
        },
    }


def _search_products_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", ""))
    limit = int(arguments.get("limit", 10))
    language = arguments.get("language")
    return search_products(query, limit=limit, language=language)


def _support_knowledge_search_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", ""))
    limit_value = arguments.get("limit")
    limit = int(limit_value) if limit_value is not None else None
    return faq_search(query, limit=limit)
