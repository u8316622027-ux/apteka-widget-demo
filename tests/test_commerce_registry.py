"""The widget and model share the same uncached commerce tools."""

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
    assert descriptor["_meta"]["ui"]["visibility"] == ["model", "app"]
    assert descriptor["annotations"]["readOnlyHint"] is (name == "my_cart")
    assert server._get_tool_cache_ttl_seconds(name) is None
    result = tool_registry.decorate_tool_result(name, tool, {})
    assert result["widget"]["open"]["page"] == page
