"""Tests for theme tool behavior."""

from __future__ import annotations

from app.interfaces.mcp import server as mcp_server
from app.interfaces.mcp import tool_registry


def test_set_widget_theme_manual_disables_auto() -> None:
    handler = tool_registry.create_tool_registry()["set_widget_theme"].handler

    payload = handler({"theme": "dark"})

    assert payload["theme"] == "dark"
    assert payload["theme_mode"] == "manual"
    assert payload["auto_disabled"] is True
    assert "Автоподбор темы отключён" in payload["assistant_notice"]


def test_set_widget_theme_auto_enables_auto() -> None:
    handler = tool_registry.create_tool_registry()["set_widget_theme"].handler

    payload = handler({"theme": "auto"})

    assert payload["theme"] == "auto"
    assert payload["theme_mode"] == "auto"
    assert payload["auto_disabled"] is False
    assert "Автоподбор темы включён" in payload["assistant_notice"]


def test_server_theme_handler_matches_registry() -> None:
    handler = mcp_server.create_tool_registry()["set_widget_theme"].handler

    payload = handler({"theme": "light"})

    assert payload["theme"] == "light"
    assert payload["theme_mode"] == "manual"
    assert payload["auto_disabled"] is True
    assert "Автоподбор темы отключён" in payload["assistant_notice"]
