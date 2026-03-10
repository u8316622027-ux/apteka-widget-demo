"""Tests for MCP server helpers and request handling."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.interfaces.mcp import server as mcp_server
from app.interfaces.mcp import tool_registry


def test_create_tool_registry_uses_base_handlers() -> None:
    base_registry = tool_registry.create_tool_registry()
    server_registry = mcp_server.create_tool_registry()

    for name in ("search_products", "support_knowledge_search", "set_widget_theme"):
        assert server_registry[name].handler is base_registry[name].handler


def test_resolve_widget_page_varies_by_tool() -> None:
    assert tool_registry._resolve_widget_page("search_products") == "search"
    assert tool_registry._resolve_widget_page("support_knowledge_search") == "support"


def test_inline_local_widget_assets_inlines_local_files() -> None:
    base_temp = Path(__file__).resolve().parent / ".tmp"
    base_temp.mkdir(parents=True, exist_ok=True)
    widget_dir = base_temp / f"widget-{uuid4().hex}"
    styles_dir = widget_dir / "styles"
    scripts_dir = widget_dir / "scripts"
    styles_dir.mkdir(parents=True)
    scripts_dir.mkdir(parents=True)

    css_text = ".hello{color:red;}"
    js_text = "console.log('hello');"
    (styles_dir / "widget.css").write_text(css_text, encoding="utf-8")
    (scripts_dir / "widget.js").write_text(js_text, encoding="utf-8")

    html = (
        '<link rel="stylesheet" href="./styles/widget.css" />\n'
        '<script src="./scripts/widget.js"></script>\n'
        '<link rel="stylesheet" href="../secrets.css" />\n'
    )

    result = mcp_server._inline_local_widget_assets(html, widget_dir=widget_dir)

    assert css_text in result
    assert js_text in result
    assert "../secrets.css" in result


def test_build_tool_success_text_round_trips_payload() -> None:
    payload = {"status": "ok", "count": 2, "items": ["a", "b"]}
    encoded = mcp_server._build_tool_success_text(payload)

    assert json.loads(encoded) == payload


def test_handle_rpc_request_tool_error_omits_http_request_id() -> None:
    def _boom(_: dict[str, object]) -> dict[str, object]:
        raise ValueError("boom")

    registry = {
        "demo": tool_registry.ToolDefinition(
            name="demo",
            description="demo",
            input_schema={"type": "object", "properties": {}},
            handler=_boom,
            output_template="",
            ui={},
        )
    }

    response = mcp_server.handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {"name": "demo", "arguments": {}},
        },
        registry=registry,
        http_request_id="req-123",
    )

    error_payload = response["result"]["structuredContent"]["error"]
    assert "http_request_id" not in error_payload


def test_handle_jsonrpc_payload_notification_returns_none() -> None:
    response = mcp_server.handle_jsonrpc_payload({"jsonrpc": "2.0", "method": "initialize"})

    assert response is None


def test_tools_list_cache_refreshes_after_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_WIDGET_DOMAIN", "https://example-a.test")
    mcp_server._reset_server_caches_for_tests()
    first = mcp_server._get_default_tools_list_payload()

    monkeypatch.setenv("MCP_WIDGET_DOMAIN", "https://example-b.test")
    mcp_server._reset_server_caches_for_tests()
    second = mcp_server._get_default_tools_list_payload()

    assert first != second
    assert second["tools"][0]["ui"]["domain"] == "https://example-b.test"


def test_build_access_log_message_sanitizes_user_agent() -> None:
    user_agent = "Test/1.0\r\nWith-Newline " + ("x" * 200)
    message = mcp_server._build_access_log_message(
        method="POST",
        path="/mcp",
        status_code=200,
        latency_ms=3.5,
        client_ip="127.0.0.1",
        user_agent=user_agent,
        request_id="req-1",
    )

    assert "\n" not in message
    assert "\r" not in message
    assert "..." in message


def test_parse_content_length_rejects_missing() -> None:
    headers = {"Content-Type": "application/json"}

    with pytest.raises(ValueError, match="Content-Length"):
        mcp_server._parse_content_length(headers)
