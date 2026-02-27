"""Tests for the minimal MCP HTTP server request handling."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.interfaces.mcp.server import create_tool_registry, handle_rpc_request


class MCPServerTests(unittest.TestCase):
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
                "faq_search",
                "my_cart",
                "search_products",
                "set_widget_theme",
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

    def test_unknown_method_returns_jsonrpc_error(self) -> None:
        registry = create_tool_registry()

        response = handle_rpc_request(
            {"jsonrpc": "2.0", "id": 4, "method": "unknown/method", "params": {}},
            registry=registry,
        )

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
