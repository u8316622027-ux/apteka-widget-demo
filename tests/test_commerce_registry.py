"""Old clients retain callable handlers without advertising them in MCP discovery."""

from dataclasses import replace

import pytest

from app.interfaces.mcp import server, tool_registry


@pytest.mark.parametrize(
    "name,page",
    [
        ("my_cart", "cart"),
        ("add_to_my_cart", "cart"),
        ("checkout_order", "checkout"),
    ],
)
def test_commerce_tools_are_accessible_uncached_and_open_the_right_page(name, page):
    tool = tool_registry.create_tool_registry()[name]
    descriptor = tool_registry.serialize_tool_definition(tool)
    assert descriptor["_meta"]["openai/widgetAccessible"] is True
    assert descriptor["_meta"]["ui"]["visibility"] == ["app"]
    assert descriptor["annotations"]["readOnlyHint"] is False
    assert server._get_tool_cache_ttl_seconds(name) is None
    result = tool_registry.decorate_tool_result(name, tool, {})
    assert result["widget"]["open"]["page"] == page


@pytest.mark.parametrize(
    "name",
    [
        "my_cart",
        "add_to_my_cart",
        "checkout_order",
    ],
)
def test_old_clients_can_call_unlisted_compatibility_handlers(name):
    registry = tool_registry.create_tool_registry()
    calls = []

    def handler(arguments):
        calls.append(arguments)
        return {"status": "compatibility_ok"}

    registry[name] = replace(registry[name], handler=handler)
    advertised = server.handle_rpc_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        registry=registry,
    )
    assert name not in {tool["name"] for tool in advertised["result"]["tools"]}
    arguments = {"cart_session_id": "legacy"} if name == "checkout_order" else {}
    response = server.handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        registry=registry,
    )
    assert response["result"]["structuredContent"]["status"] == "compatibility_ok"
    assert calls == [arguments]
