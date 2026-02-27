"""Shared MCP tool context helpers."""

from __future__ import annotations


def normalize_cart_session_id(value: object) -> str | None:
    """Normalize incoming cart session id from tool arguments."""

    if value is None:
        return None
    session_id = str(value).strip()
    return session_id or None
