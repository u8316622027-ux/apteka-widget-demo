"""Tests for centralized settings loading."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from app.core.config import AppSettings, get_settings


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_settings_load_from_dotenv_file(self) -> None:
        env_path = Path("tests/.tmp-config.env")
        env_path.write_text(
            "\n".join(
                [
                    "UPSTASH_REDIS_REST_URL=https://example.upstash.io",
                    "UPSTASH_REDIS_REST_TOKEN=secret",
                    "CART_TOKEN_TTL_SECONDS=321",
                    "MCP_SEARCH_CACHE_TTL_SECONDS=17",
                    "MCP_TRACKING_CACHE_TTL_SECONDS=9",
                    "MCP_CHECKOUT_REFERENCE_CACHE_TTL_SECONDS=222",
                    "MCP_TOOL_CACHE_MAX_ENTRIES=77",
                ]
            ),
            encoding="utf-8",
        )

        try:
            settings = AppSettings(_env_file=env_path)
        finally:
            env_path.unlink(missing_ok=True)

        self.assertEqual(settings.upstash_redis_rest_url, "https://example.upstash.io")
        self.assertEqual(settings.upstash_redis_rest_token, "secret")
        self.assertEqual(settings.cart_token_ttl_seconds, 321)
        self.assertEqual(settings.mcp_search_cache_ttl_seconds, 17)
        self.assertEqual(settings.mcp_tracking_cache_ttl_seconds, 9)
        self.assertEqual(settings.mcp_checkout_reference_cache_ttl_seconds, 222)
        self.assertEqual(settings.mcp_tool_cache_max_entries, 77)

    def test_get_settings_is_cached(self) -> None:
        with unittest.mock.patch.dict(os.environ, {}, clear=False):
            first = get_settings()
            second = get_settings()

        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
