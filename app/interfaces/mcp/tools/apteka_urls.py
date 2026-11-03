"""Shared apteka endpoint URL builders."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.core.env import read_env_file_value

ENV_FILE_PATH = Path(__file__).resolve().parents[4] / ".env"


def get_apteka_media_base_url() -> str:
    """Product media can stay on production while order APIs use stage."""
    raw = str(os.getenv("APTEKA_MEDIA_BASE_URL", "")).strip()
    if not raw:
        raw = read_env_file_value("APTEKA_MEDIA_BASE_URL", env_path=ENV_FILE_PATH).strip()
    return (raw or "https://api.apteka.md").rstrip("/")


def resolve_apteka_image_url(value: str | None) -> str | None:
    if not value:
        return value
    parsed = urlsplit(value)
    apteka_host = parsed.hostname in {"stage.apteka.md", "api.apteka.md", "www.apteka.md"}
    relative = not parsed.scheme and not parsed.netloc and value.startswith("/")
    if (apteka_host or relative) and parsed.path.startswith(("/media/", "/assets/images/")):
        media = urlsplit(get_apteka_media_base_url())
        return urlunsplit((media.scheme, media.netloc, parsed.path, parsed.query, parsed.fragment))
    return value


def get_apteka_base_url() -> str:
    raw = str(os.getenv("APTEKA_BASE_URL", "")).strip()
    if raw:
        return raw.rstrip("/")
    from_file = read_env_file_value("APTEKA_BASE_URL", env_path=ENV_FILE_PATH).strip()
    if from_file:
        return from_file.rstrip("/")
    raise RuntimeError("APTEKA_BASE_URL is required and must be set in env or .env")


def build_front_url(path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{get_apteka_base_url()}/api/v1/front{normalized_path}"


def build_api_url(path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{get_apteka_base_url()}{normalized_path}"
