"""Minimal MCP HTTP server with tool registration."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

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
    return add_to_my_cart(
        product_id=product_id,
        quantity=quantity,
        items=items,
        cart_session_id=str(cart_session_id) if cart_session_id is not None else None,
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
        comment=str(comment) if comment is not None else None,
    )


def create_tool_registry() -> dict[str, ToolDefinition]:
    """Create the default tool registry for MCP requests."""

    return {
        "search_products": ToolDefinition(
            name="search_products",
            description="Search products by query in apteka catalog.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["query"],
            },
            handler=_search_products_handler,
        ),
        "add_to_my_cart": ToolDefinition(
            name="add_to_my_cart",
            description=(
                "Manage cart with two modes. "
                "Single add: pass only product_id and optional cart_session_id; "
                "server uses /cart/add. "
                "Batch update: pass items=[{product_id,quantity},...], "
                "where quantity is absolute target and 0 removes item; "
                "server uses /cart/update."
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
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "string"},
                                "quantity": {"type": "integer", "minimum": 0},
                            },
                            "required": ["product_id", "quantity"],
                        },
                    },
                    "cart_session_id": {"type": "string"},
                },
                "anyOf": [{"required": ["product_id"]}, {"required": ["items"]}],
            },
            handler=_add_to_my_cart_handler,
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
                    "comment": {"type": "string"},
                },
            },
            handler=_checkout_order_handler,
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
        ),
        "my_cart": ToolDefinition(
            name="my_cart",
            description="Get current user cart state.",
            input_schema={
                "type": "object",
                "properties": {"cart_session_id": {"type": "string"}},
            },
            handler=_my_cart_handler,
        ),
        "set_widget_theme": ToolDefinition(
            name="set_widget_theme",
            description="Set storefront widget theme.",
            input_schema={"type": "object"},
            handler=_not_implemented_tool("set_widget_theme"),
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
        ),
    }


def handle_rpc_request(
    request_payload: dict[str, Any],
    *,
    registry: dict[str, ToolDefinition] | None = None,
) -> dict[str, Any]:
    """Handle a single JSON-RPC request."""

    active_registry = registry or create_tool_registry()
    request_id = request_payload.get("id")
    method = request_payload.get("method")
    params = request_payload.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "apteka-mcp", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in active_registry.values()
                ]
            },
        }

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        tool = active_registry.get(tool_name)
        if tool is None:
            return _rpc_error(request_id, -32601, f"Tool not found: {tool_name}")

        try:
            result_payload = tool.handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result_payload, ensure_ascii=False)}
                    ],
                    "structuredContent": result_payload,
                    "isError": False,
                },
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    return _rpc_error(request_id, -32601, f"Method not found: {method}")


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


class MCPHttpHandler(BaseHTTPRequestHandler):
    """HTTP transport for minimal MCP JSON-RPC methods."""

    server_version = "AptekaMCP/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send_json({"status": "ok"})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/mcp":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            request_payload = json.loads(raw_body.decode("utf-8"))
            response_payload = handle_rpc_request(request_payload)
            self._send_json(response_payload)
        except json.JSONDecodeError:
            self._send_json(_rpc_error(None, -32700, "Parse error"), status=HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep server output concise in local development.
        return

    def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run MCP HTTP server."""

    server = ThreadingHTTPServer((host, port), MCPHttpHandler)
    print(f"MCP server started on http://{host}:{port}/mcp")
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run minimal MCP HTTP server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
