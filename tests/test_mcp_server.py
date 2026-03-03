"""Tests for the minimal MCP HTTP server request handling."""

from __future__ import annotations

import http.client
import json
import threading
import unittest
from unittest.mock import patch

from app.interfaces.mcp.server import (
    _is_json_content_type,
    _resolve_http_request_id,
    MCPHttpHandler,
    ThreadingHTTPServer,
    create_tool_registry,
    handle_jsonrpc_payload,
    handle_rpc_request,
)


class MCPServerTests(unittest.TestCase):
    def test_resolve_http_request_id_prefers_incoming_header(self) -> None:
        self.assertEqual(_resolve_http_request_id("req-123"), "req-123")

    def test_resolve_http_request_id_generates_when_missing(self) -> None:
        generated = _resolve_http_request_id(None)
        self.assertIsInstance(generated, str)
        self.assertTrue(len(generated) >= 8)

    def test_json_content_type_allows_application_json_with_charset(self) -> None:
        self.assertTrue(_is_json_content_type("application/json"))
        self.assertTrue(_is_json_content_type("application/json; charset=utf-8"))
        self.assertFalse(_is_json_content_type("text/plain"))

    def test_handle_jsonrpc_payload_supports_batch_requests(self) -> None:
        registry = create_tool_registry()
        response = handle_jsonrpc_payload(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ],
            registry=registry,
        )

        self.assertIsInstance(response, list)
        assert isinstance(response, list)
        self.assertEqual(len(response), 2)
        self.assertEqual(response[0]["id"], 1)
        self.assertEqual(response[1]["id"], 2)

    def test_handle_jsonrpc_payload_returns_invalid_request_for_empty_batch(self) -> None:
        response = handle_jsonrpc_payload([])

        self.assertIsInstance(response, dict)
        assert isinstance(response, dict)
        self.assertEqual(response["error"]["code"], -32600)

    def test_handle_jsonrpc_payload_notification_returns_none(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.search_products",
            return_value={"query": "цитрамон", "count": 1, "products": [{"id": 1}]},
        ) as mocked_search:
            response = handle_jsonrpc_payload(
                {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_products",
                        "arguments": {"query": "цитрамон", "limit": 5},
                    },
                },
                registry=registry,
            )

        mocked_search.assert_called_once_with("цитрамон", limit=5)
        self.assertIsNone(response)

    def test_invalid_request_payload_type_returns_invalid_request_error(self) -> None:
        response = handle_rpc_request("not-a-dict")  # type: ignore[arg-type]

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32600)

    def test_initialize_returns_server_info(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            registry=registry,
        )

        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertIn("result", response)
        self.assertEqual(response["result"]["serverInfo"]["name"], "apteka-mcp")

    def test_tools_list_contains_required_tools(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            registry=registry,
        )

        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertSetEqual(
            names,
            {
                "add_to_my_cart",
                "checkout_order",
                "my_cart",
                "search_products",
                "set_widget_theme",
                "support_knowledge_search",
                "track_order_status_ui",
            },
        )

    def test_tools_call_search_products_delegates_to_tool_function(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.search_products",
            return_value={"query": "цитрамон", "count": 1, "products": [{"id": 1}]},
        ) as mocked_search:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "search_products",
                        "arguments": {"query": "цитрамон", "limit": 5},
                    },
                },
                registry=registry,
            )

        mocked_search.assert_called_once_with("цитрамон", limit=5)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["count"], 1)

    def test_tools_call_success_uses_compact_summary_text_content(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.search_products",
            return_value={
                "query": "цитрамон",
                "count": 2,
                "products": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
                "extra": "x" * 1000,
            },
        ):
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 303,
                    "method": "tools/call",
                    "params": {
                        "name": "search_products",
                        "arguments": {"query": "цитрамон", "limit": 5},
                    },
                },
                registry=registry,
            )

        text_content = response["result"]["content"][0]["text"]
        self.assertIn('"ok":true', text_content)
        self.assertIn('"count":2', text_content)
        self.assertNotIn('"products":[', text_content)
        self.assertNotIn("xxxxxxxx", text_content)

    def test_unknown_method_returns_jsonrpc_error(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}},
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)

    def test_tools_call_requires_string_name(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"arguments": {"query": "цитрамон"}},
            },
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_requires_object_arguments(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {"name": "search_products", "arguments": ["bad"]},
            },
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_validates_required_fields_from_schema(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {"name": "search_products", "arguments": {}},
            },
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_validates_argument_types_from_schema(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {
                "jsonrpc": "2.0",
                "id": 14,
                "method": "tools/call",
                "params": {"name": "search_products", "arguments": {"query": "q", "limit": "5"}},
            },
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_validates_any_of_for_add_to_cart(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {
                "jsonrpc": "2.0",
                "id": 15,
                "method": "tools/call",
                "params": {"name": "add_to_my_cart", "arguments": {"cart_session_id": "sess-1"}},
            },
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_error_returns_structured_error_payload(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.search_products",
            side_effect=TimeoutError("external api timeout"),
        ):
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": "req-42",
                    "method": "tools/call",
                    "params": {
                        "name": "search_products",
                        "arguments": {"query": "цитрамон", "limit": 5},
                    },
                },
                registry=registry,
            )

        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("structuredContent", response["result"])
        error_payload = response["result"]["structuredContent"]["error"]
        self.assertEqual(error_payload["request_id"], "req-42")
        self.assertEqual(error_payload["retriable"], True)
        self.assertEqual(error_payload["type"], "timeout_error")
        self.assertIn("timeout", error_payload["message"].lower())

    def test_tools_call_error_logs_with_request_id(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.search_products",
            side_effect=RuntimeError("boom"),
        ):
            with patch("app.interfaces.mcp.server.logger") as mocked_logger:
                response = handle_rpc_request(
                    {
                        "jsonrpc": "2.0",
                        "id": "req-log-1",
                        "method": "tools/call",
                        "params": {
                            "name": "search_products",
                            "arguments": {"query": "цитрамон", "limit": 5},
                        },
                    },
                    registry=registry,
                    http_request_id="http-req-1",
                )

        self.assertTrue(response["result"]["isError"])
        mocked_logger.exception.assert_called_once()
        _, kwargs = mocked_logger.exception.call_args
        self.assertIn("extra", kwargs)
        self.assertEqual(kwargs["extra"]["rpc_request_id"], "req-log-1")
        self.assertEqual(kwargs["extra"]["http_request_id"], "http-req-1")
        self.assertEqual(kwargs["extra"]["tool_name"], "search_products")

    def test_track_order_status_tool_description_mentions_supported_inputs(self) -> None:
        registry = create_tool_registry()

        tool = registry["track_order_status_ui"]

        self.assertIn("order number", tool.description.lower())
        self.assertIn("phone", tool.description.lower())
        self.assertIn("country code", tool.description.lower())
        self.assertIn("operator", tool.description.lower())
        self.assertIn("wait", tool.description.lower())
        self.assertIn("status_hint", tool.description.lower())
        self.assertIn("packed", tool.description.lower())

    def test_tools_call_track_order_status_delegates_to_tracking_tool(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.track_order_status_ui",
            return_value={"lookup": "ORD-123", "count": 1, "orders": [{"status": "processing"}]},
        ) as mocked_tracking:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "track_order_status_ui",
                        "arguments": {"lookup": "ORD-123"},
                    },
                },
                registry=registry,
            )

        mocked_tracking.assert_called_once_with("ORD-123")
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["count"], 1)

    def test_support_knowledge_search_tool_description_mentions_use_cases(self) -> None:
        registry = create_tool_registry()

        tool = registry["support_knowledge_search"]

        self.assertIn("faq", tool.description.lower())
        self.assertIn("order", tool.description.lower())
        self.assertIn("work schedule", tool.description.lower())
        self.assertIn("app", tool.description.lower())

    def test_tools_call_support_knowledge_search_delegates_to_faq_tool(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.faq_search",
            return_value={
                "query": "как оформить заказ",
                "count": 1,
                "chunks": [{"id": 10, "text": "Через корзину"}],
            },
        ) as mocked_faq_search:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "support_knowledge_search",
                        "arguments": {"query": "как оформить заказ", "limit": 3},
                    },
                },
                registry=registry,
            )

        mocked_faq_search.assert_called_once_with("как оформить заказ", limit=3)
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["count"], 1)

    def test_tools_call_my_cart_delegates_to_cart_tool(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.my_cart",
            return_value={"cart_session_id": "sess-1", "count": 0, "items": []},
        ) as mocked_my_cart:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "my_cart",
                        "arguments": {"cart_session_id": "sess-1"},
                    },
                },
                registry=registry,
            )

        mocked_my_cart.assert_called_once_with(cart_session_id="sess-1")
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["cart_session_id"], "sess-1")

    def test_tools_call_add_to_my_cart_delegates_to_cart_tool(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.add_to_my_cart",
            return_value={
                "cart_session_id": "sess-1",
                "count": 1,
                "items": [{"product_id": "A12", "quantity": 2}],
            },
        ) as mocked_add_to_cart:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "add_to_my_cart",
                        "arguments": {
                            "cart_session_id": "sess-1",
                            "product_id": "A12",
                            "quantity": 2,
                        },
                    },
                },
                registry=registry,
            )

        mocked_add_to_cart.assert_called_once_with(
            product_id="A12",
            quantity=2,
            items=None,
            cart_session_id="sess-1",
        )
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["count"], 1)

    def test_tools_call_add_to_my_cart_batch_items_delegates_to_cart_tool(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.add_to_my_cart",
            return_value={
                "cart_session_id": "sess-1",
                "count": 2,
                "items": [
                    {"product_id": "16174", "quantity": 1},
                    {"product_id": "20859", "quantity": 1},
                ],
            },
        ) as mocked_add_to_cart:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "add_to_my_cart",
                        "arguments": {
                            "cart_session_id": "sess-1",
                            "items": [{"product_id": "20859", "quantity": 1}],
                        },
                    },
                },
                registry=registry,
            )

        mocked_add_to_cart.assert_called_once_with(
            product_id=None,
            quantity=None,
            items=[{"product_id": "20859", "quantity": 1}],
            cart_session_id="sess-1",
        )
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["count"], 2)

    def test_tools_call_checkout_order_delegates_to_checkout_tool(self) -> None:
        registry = create_tool_registry()
        with patch(
            "app.interfaces.mcp.server.checkout_order",
            return_value={"status": "delivery_method_selection", "cart_count": 1},
        ) as mocked_checkout:
            response = handle_rpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "name": "checkout_order",
                        "arguments": {"cart_session_id": "sess-1"},
                    },
                },
                registry=registry,
            )

        mocked_checkout.assert_called_once_with(
            cart_session_id="sess-1",
            delivery_method=None,
            pickup_region_id=None,
            pickup_region_name=None,
            pickup_city_id=None,
            pickup_city_name=None,
            pickup_pharmacy_id=None,
            pickup_pharmacy_name=None,
            pickup_contact=None,
            courier_contact=None,
            courier_address=None,
            payment_method=None,
            dont_call_me=None,
            terms_accepted=None,
            comment=None,
        )
        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["structuredContent"]["status"], "delivery_method_selection")

    def test_checkout_order_schema_contains_courier_address_and_contact(self) -> None:
        registry = create_tool_registry()
        checkout_tool = registry["checkout_order"]
        properties = checkout_tool.input_schema["properties"]

        self.assertIn("courier_contact", properties)
        self.assertIn("courier_address", properties)


class MCPHttpTransportRequestIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHttpHandler)
        cls._host, cls._port = cls._server.server_address
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.shutdown()
        cls._server.server_close()
        cls._thread.join(timeout=2)

    def _post_mcp(self, payload: dict[str, object], headers: dict[str, str] | None = None):
        body = json.dumps(payload).encode("utf-8")
        request_headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        if headers:
            request_headers.update(headers)

        connection = http.client.HTTPConnection(self._host, self._port, timeout=5)
        connection.request("POST", "/mcp", body=body, headers=request_headers)
        response = connection.getresponse()
        raw_body = response.read()
        headers_map = {key.lower(): value for key, value in response.getheaders()}
        status_code = response.status
        connection.close()
        return status_code, headers_map, raw_body

    def test_http_response_includes_incoming_x_request_id(self) -> None:
        status, headers, _ = self._post_mcp(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers={"X-Request-Id": "incoming-req-42"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("x-request-id"), "incoming-req-42")

    def test_http_response_generates_x_request_id_when_missing(self) -> None:
        status, headers, _ = self._post_mcp(
            {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
        )
        self.assertEqual(status, 200)
        self.assertIn("x-request-id", headers)
        self.assertTrue(len(headers["x-request-id"]) >= 8)


if __name__ == "__main__":
    unittest.main()
