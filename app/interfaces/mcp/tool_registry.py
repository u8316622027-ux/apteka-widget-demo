"""MCP tool registry and serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.config import get_settings
from app.interfaces.mcp.tools.apteka_urls import get_apteka_base_url
from app.interfaces.mcp.tools.faq_tools import faq_search
from app.interfaces.mcp.tools.search_tools import search_products


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
        "set_widget_theme": ToolDefinition(
            name="set_widget_theme",
            description="Set storefront widget theme (light, dark, or auto).",
            input_schema={
                "type": "object",
                "properties": {"theme": {"type": "string"}},
            },
            handler=_set_widget_theme_handler,
            output_template="",
            ui=widget_ui_config,
        ),
    }


def serialize_tool_definition(tool: ToolDefinition) -> dict[str, Any]:
    ui_domain = str(tool.ui.get("domain") or "").strip()
    payload = {
        "name": tool.name,
        "description": tool.description,
        "inputSchema": tool.input_schema,
        "ui": tool.ui,
        "_meta": {
            "openai/widgetAccessible": True,
            "openai/widgetCSP": tool.ui.get("csp") or {},
        },
    }
    if not ui_domain:
        payload["_meta"]["openai/widgetDomain"] = ""
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


def _search_products_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", ""))
    limit = int(arguments.get("limit", 10))
    return search_products(query, limit=limit)


def _support_knowledge_search_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query", ""))
    limit_value = arguments.get("limit")
    limit = int(limit_value) if limit_value is not None else None
    return faq_search(query, limit=limit)


def _set_widget_theme_handler(arguments: dict[str, Any]) -> dict[str, Any]:
    raw_theme = str(arguments.get("theme", "default")).strip().lower()
    if raw_theme.startswith("dark") or raw_theme.startswith("тём"):
        normalized = "dark"
    elif raw_theme.startswith("light") or raw_theme.startswith("свет"):
        normalized = "light"
    elif raw_theme in {"auto", "automatic", "default", "system", ""}:
        normalized = "auto"
    else:
        normalized = "auto"
    is_auto = normalized == "auto"
    theme_mode = "auto" if is_auto else "manual"
    theme_value = normalized
    return {
        "status": "applied",
        "theme": theme_value,
        "theme_mode": theme_mode,
        "auto_disabled": not is_auto,
        "assistant_notice": (
            "Автоподбор темы отключён. Тема зафиксирована, но её всегда можно сменить позже."
            if not is_auto
            else "Автоподбор темы включён. Цвет будет меняться автоматически."
        ),
    }
