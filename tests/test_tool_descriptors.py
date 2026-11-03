"""Tests for tool descriptor metadata."""

from __future__ import annotations

import pytest

from app.interfaces.mcp import server as mcp_server
from app.interfaces.mcp import tool_registry


def test_tool_descriptor_includes_ui_meta_for_widget() -> None:
    registry = tool_registry.create_tool_registry()
    payload = tool_registry.serialize_tool_definition(registry["search_products"])

    assert payload["outputTemplate"] == "ui://widget/products.html?v=kokiko-2"
    assert payload["_meta"]["openai/outputTemplate"] == payload["outputTemplate"]
    assert payload["_meta"]["ui"]["resourceUri"] == payload["outputTemplate"]
    assert payload["_meta"]["openai/widgetDomain"]
    assert payload["_meta"]["openai/widgetCSP"]["connect_domains"]
    assert payload["_meta"]["openai/widgetCSP"]["resource_domains"]


@pytest.mark.parametrize(
    "uri",
    [
        "ui://widget/products.html?v=kokiko-2",
        "ui://widget/products.html",
    ],
)
def test_versioned_resource_and_old_connection_both_serve_current_modal(uri):
    mcp_server._reset_server_caches_for_tests()
    response = mcp_server.handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/read",
            "params": {"uri": uri},
        }
    )
    assert "error" not in response
    content = response["result"]["contents"][0]
    assert content["uri"] == uri
    assert 'id="products-cart-panel"' in content["text"]
    assert 'id="products-checkout-flow"' in content["text"]
    assert "window.ProductsApi" in content["text"]


def test_all_widget_tools_use_the_same_versioned_template():
    registry = tool_registry.create_tool_registry()
    assert {tool.output_template for tool in registry.values() if tool.output_template} == {
        "ui://widget/products.html?v=kokiko-2"
    }


def test_tool_descriptor_includes_invocation_messages() -> None:
    registry = tool_registry.create_tool_registry()
    payload = tool_registry.serialize_tool_definition(registry["search_products"])

    assert payload["_meta"]["openai/toolInvocation/invoking"]
    assert payload["_meta"]["openai/toolInvocation/invoked"]


def test_tool_descriptor_readonly_annotations() -> None:
    registry = tool_registry.create_tool_registry()
    search_payload = tool_registry.serialize_tool_definition(registry["search_products"])
    support_payload = tool_registry.serialize_tool_definition(registry["support_knowledge_search"])

    assert search_payload["annotations"] == {
        "readOnlyHint": True,
        "openWorldHint": True,
        "destructiveHint": False,
    }
    assert support_payload["annotations"] == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }


def test_theme_tool_is_removed() -> None:
    registry = tool_registry.create_tool_registry()
    assert "set_widget_theme" not in registry


@pytest.mark.parametrize("api_base", ["https://api.apteka.md", "https://stage.apteka.md"])
def test_widget_ui_config_includes_resource_and_connect_domains(
    monkeypatch: pytest.MonkeyPatch,
    api_base: str,
) -> None:
    monkeypatch.setenv("MCP_WIDGET_DOMAIN", "https://widgets.example")
    monkeypatch.setenv("APTEKA_BASE_URL", api_base)
    monkeypatch.setenv("APTEKA_MEDIA_BASE_URL", "https://api.apteka.md")
    mcp_server._reset_server_caches_for_tests()

    registry = tool_registry.create_tool_registry()
    ui_config = registry["search_products"].ui
    csp = ui_config["csp"]

    assert "https://widgets.example" in csp["resourceDomains"]
    assert api_base in csp["connectDomains"]
    assert api_base in csp["resourceDomains"]
    assert "https://api.apteka.md" in csp["resourceDomains"]
    assert csp["connectDomains"] == [api_base]
    assert "https://cdn.jsdelivr.net" not in csp["resourceDomains"]


def test_resources_list_uses_snakecase_csp_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_WIDGET_DOMAIN", "https://widgets.example")
    mcp_server._reset_server_caches_for_tests()

    response = mcp_server.handle_rpc_request(
        {"jsonrpc": "2.0", "id": "1", "method": "resources/list"}
    )

    resource_meta = response["result"]["resources"][0]["_meta"]
    widget_csp = resource_meta["openai/widgetCSP"]

    assert "connect_domains" in widget_csp
    assert "resource_domains" in widget_csp
