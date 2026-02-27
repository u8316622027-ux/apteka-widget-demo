"""Centralized application settings."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - fallback for constrained environments
    BaseSettings = None  # type: ignore[assignment]
    Field = None  # type: ignore[assignment]
    SettingsConfigDict = None  # type: ignore[assignment]


def _to_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        cleaned = value.strip().strip("'").strip('"')
        values[key.strip()] = cleaned
    return values


if BaseSettings is not None:

    class AppSettings(BaseSettings):
        """Typed application settings loaded from environment and `.env`."""

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

        upstash_redis_rest_url: str = ""
        upstash_redis_rest_token: str = ""
        redis_url: str = ""
        cart_token_ttl_seconds: int = Field(default=604800, gt=0)

else:

    @dataclass(frozen=True, slots=True)
    class AppSettings:
        """Fallback settings loader with `.env` support."""

        upstash_redis_rest_url: str = ""
        upstash_redis_rest_token: str = ""
        redis_url: str = ""
        cart_token_ttl_seconds: int = 604800

        def __init__(self, _env_file: str | Path | None = None) -> None:
            env_path = Path(_env_file) if _env_file else Path(".env")
            file_env = _read_env_file(env_path)
            merged = dict(file_env)
            merged.update({k: v for k, v in os.environ.items() if isinstance(v, str)})

            object.__setattr__(
                self,
                "upstash_redis_rest_url",
                str(merged.get("UPSTASH_REDIS_REST_URL", "")).strip(),
            )
            object.__setattr__(
                self,
                "upstash_redis_rest_token",
                str(merged.get("UPSTASH_REDIS_REST_TOKEN", "")).strip(),
            )
            object.__setattr__(
                self,
                "redis_url",
                str(merged.get("REDIS_URL", "")).strip(),
            )
            object.__setattr__(
                self,
                "cart_token_ttl_seconds",
                _to_int(merged.get("CART_TOKEN_TTL_SECONDS"), 604800),
            )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return cached settings singleton for the running process."""

    return AppSettings()
