"""Minimal MCP HTTP server with tool registration."""

from __future__ import annotations

import argparse
import json
import logging
from functools import lru_cache
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from uuid import uuid4

from app.interfaces.mcp.tools.cart_tools import add_to_my_cart, my_cart
from app.interfaces.mcp.tools.checkout_tools import checkout_order
from app.interfaces.mcp.tools.faq_tools import faq_search
from app.interfaces.mcp.tools.search_tools import search_products
from app.interfaces.mcp.tools.tracking_tools import track_order_status_ui

MAX_REQUEST_BODY_BYTES = 1024 * 1024
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


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


@lru_cache(maxsize=1)
def _get_default_tool_registry() -> dict[str, ToolDefinition]:
    return create_tool_registry()


@lru_cache(maxsize=1)
def _get_default_tools_list_payload() -> dict[str, Any]:
    registry = _get_default_tool_registry()
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in registry.values()
        ]
    }


def _reset_server_caches_for_tests() -> None:
    _get_default_tool_registry.cache_clear()
    _get_default_tools_list_payload.cache_clear()


def handle_rpc_request(
    request_payload: dict[str, Any],
    *,
    registry: dict[str, ToolDefinition] | None = None,
    http_request_id: str | None = None,
) -> dict[str, Any]:
    """Handle a single JSON-RPC request."""

    if not isinstance(request_payload, dict):
        return _rpc_error(None, -32600, "Invalid Request")

    active_registry = registry or _get_default_tool_registry()
    request_id = request_payload.get("id")
    method = request_payload.get("method")
    raw_params = request_payload.get("params")
    if raw_params is None:
        params: dict[str, Any] = {}
    elif isinstance(raw_params, dict):
        params = raw_params
    else:
        return _rpc_error(request_id, -32602, "Invalid params: params must be an object")

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
        if registry is None:
            tools_result = _get_default_tools_list_payload()
        else:
            tools_result = {
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.input_schema,
                    }
                    for tool in active_registry.values()
                ]
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": tools_result,
        }

    if method == "tools/call":
        tool_name = params.get("name")
        if not isinstance(tool_name, str) or not tool_name.strip():
            return _rpc_error(request_id, -32602, "Invalid params: name must be a non-empty string")

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _rpc_error(request_id, -32602, "Invalid params: arguments must be an object")

        tool = active_registry.get(tool_name)
        if tool is None:
            return _rpc_error(request_id, -32601, f"Tool not found: {tool_name}")

        validation_error = _validate_input_schema(arguments, tool.input_schema)
        if validation_error is not None:
            return _rpc_error(request_id, -32602, f"Invalid params: {validation_error}")

        try:
            result_payload = tool.handler(arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": _build_tool_success_text(result_payload)}],
                    "structuredContent": result_payload,
                    "isError": False,
                },
            }
        except Exception as exc:  # noqa: BLE001
            error_payload = _classify_tool_error(exc)
            logger.exception(
                "mcp_tool_call_failed",
                extra={
                    "http_request_id": http_request_id,
                    "rpc_request_id": request_id,
                    "tool_name": tool_name,
                    "error_type": error_payload["type"],
                    "retriable": error_payload["retriable"],
                },
            )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "structuredContent": {
                        "error": {
                            "type": error_payload["type"],
                            "message": error_payload["message"],
                            "retriable": error_payload["retriable"],
                            "request_id": request_id,
                            "http_request_id": http_request_id,
                        }
                    },
                    "isError": True,
                },
            }

    return _rpc_error(request_id, -32601, f"Method not found: {method}")


def handle_jsonrpc_payload(
    request_payload: Any,
    *,
    registry: dict[str, ToolDefinition] | None = None,
    http_request_id: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Handle single or batch JSON-RPC payload and support notifications."""

    if isinstance(request_payload, list):
        if not request_payload:
            return _rpc_error(None, -32600, "Invalid Request")

        responses: list[dict[str, Any]] = []
        for item in request_payload:
            if isinstance(item, dict) and "id" not in item:
                handle_rpc_request(item, registry=registry, http_request_id=http_request_id)
                continue

            response_payload = handle_rpc_request(
                item, registry=registry, http_request_id=http_request_id
            )
            responses.append(response_payload)

        return responses or None

    if isinstance(request_payload, dict) and "id" not in request_payload:
        handle_rpc_request(request_payload, registry=registry, http_request_id=http_request_id)
        return None

    return handle_rpc_request(request_payload, registry=registry, http_request_id=http_request_id)


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _validate_input_schema(arguments: dict[str, Any], schema: dict[str, Any]) -> str | None:
    return _validate_value(arguments, schema, path="arguments")


def _validate_value(value: Any, schema: dict[str, Any], *, path: str) -> str | None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            return f"{path} must be an object"

        required = schema.get("required")
        if isinstance(required, list):
            for field_name in required:
                if isinstance(field_name, str) and field_name not in value:
                    return f"{path}.{field_name} is required"

        properties = schema.get("properties")
        if isinstance(properties, dict):
            for field_name, field_schema in properties.items():
                if field_name not in value or not isinstance(field_schema, dict):
                    continue
                nested_error = _validate_value(
                    value[field_name],
                    field_schema,
                    path=f"{path}.{field_name}",
                )
                if nested_error is not None:
                    return nested_error

        any_of = schema.get("anyOf")
        if isinstance(any_of, list) and any_of:
            if not any(_matches_schema_variant(value, item) for item in any_of):
                return f"{path} must satisfy at least one anyOf schema"
        return None

    if expected_type == "array":
        if not isinstance(value, list):
            return f"{path} must be an array"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                nested_error = _validate_value(item, item_schema, path=f"{path}[{index}]")
                if nested_error is not None:
                    return nested_error
        return None

    if expected_type == "string":
        if not isinstance(value, str):
            return f"{path} must be a string"

    if expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{path} must be an integer"
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            return f"{path} must be greater than or equal to {minimum}"

    if expected_type == "boolean":
        if not isinstance(value, bool):
            return f"{path} must be a boolean"

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        return f"{path} must be one of {enum}"

    return None


def _matches_schema_variant(value: dict[str, Any], schema_variant: Any) -> bool:
    if not isinstance(schema_variant, dict):
        return False
    required = schema_variant.get("required")
    if isinstance(required, list):
        for field_name in required:
            if isinstance(field_name, str) and field_name not in value:
                return False
    return True


def _is_json_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False
    mime_type = content_type.split(";", 1)[0].strip().lower()
    return mime_type == "application/json"


def _classify_tool_error(exc: Exception) -> dict[str, Any]:
    message = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, TimeoutError):
        return {"type": "timeout_error", "message": message, "retriable": True}
    if isinstance(exc, ConnectionError):
        return {"type": "connection_error", "message": message, "retriable": True}
    if isinstance(exc, ValueError):
        return {"type": "validation_error", "message": message, "retriable": False}
    return {"type": "tool_execution_error", "message": message, "retriable": False}


def _build_tool_success_text(result_payload: dict[str, Any]) -> str:
    summary: dict[str, Any] = {"ok": True, "keys": sorted(result_payload.keys())}
    if "count" in result_payload:
        summary["count"] = result_payload.get("count")
    if "status" in result_payload:
        summary["status"] = result_payload.get("status")
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))


def _resolve_http_request_id(incoming_request_id: str | None) -> str:
    if incoming_request_id is None:
        return uuid4().hex
    normalized = incoming_request_id.strip()
    if normalized:
        return normalized
    return uuid4().hex


class MCPHttpHandler(BaseHTTPRequestHandler):
    """HTTP transport for minimal MCP JSON-RPC methods."""

    server_version = "AptekaMCP/0.1"
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        request_id = _resolve_http_request_id(self.headers.get("X-Request-Id"))
        if self.path == "/health":
            self._send_json({"status": "ok"}, request_id=request_id)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        request_id = _resolve_http_request_id(self.headers.get("X-Request-Id"))
        if self.path != "/mcp":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not _is_json_content_type(self.headers.get("Content-Type")):
            self._send_json(
                _rpc_error(None, -32600, "Invalid Request: Content-Type must be application/json"),
                status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                request_id=request_id,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length < 0:
                self._send_json(
                    _rpc_error(None, -32600, "Invalid Request: Content-Length must be non-negative"),
                    status=HTTPStatus.BAD_REQUEST,
                    request_id=request_id,
                )
                return
            if content_length > MAX_REQUEST_BODY_BYTES:
                self._send_json(
                    _rpc_error(None, -32600, "Invalid Request: body is too large"),
                    status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    request_id=request_id,
                )
                return

            raw_body = self.rfile.read(content_length)
            request_payload = json.loads(raw_body.decode("utf-8"))
            response_payload = handle_jsonrpc_payload(request_payload, http_request_id=request_id)
            if response_payload is None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("X-Request-Id", request_id)
                self.end_headers()
                return
            self._send_json(response_payload, request_id=request_id)
        except ValueError:
            self._send_json(
                _rpc_error(None, -32600, "Invalid Request: invalid Content-Length header"),
                status=HTTPStatus.BAD_REQUEST,
                request_id=request_id,
            )
        except json.JSONDecodeError:
            self._send_json(
                _rpc_error(None, -32700, "Parse error"),
                status=HTTPStatus.BAD_REQUEST,
                request_id=request_id,
            )

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep server output concise in local development.
        return

    def _send_json(
        self,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        status: HTTPStatus = HTTPStatus.OK,
        request_id: str | None = None,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        if request_id:
            self.send_header("X-Request-Id", request_id)
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
