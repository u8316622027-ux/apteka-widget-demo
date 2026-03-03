"""Shared apteka endpoint URL builders."""

from __future__ import annotations

import os

DEFAULT_APTEKA_BASE_URL = "https://stage.apteka.md"


def get_apteka_base_url() -> str:
    raw = str(os.getenv("APTEKA_BASE_URL", "")).strip()
    if raw:
        return raw.rstrip("/")
    return DEFAULT_APTEKA_BASE_URL


def build_front_url(path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{get_apteka_base_url()}/api/v1/front{normalized_path}"


def build_api_url(path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{get_apteka_base_url()}{normalized_path}"
