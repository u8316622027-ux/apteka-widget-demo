"""Tests for optional FastAPI MCP transport adapter."""

from __future__ import annotations

import gzip
import json
import unittest
from unittest.mock import patch

from app.interfaces.mcp.fastapi_server import (
    _build_json_response_bytes,
    _client_accepts_gzip,
    create_fastapi_app,
)


class MCPFastAPIServerTests(unittest.TestCase):
    def test_client_accepts_gzip_is_case_insensitive(self) -> None:
        self.assertTrue(_client_accepts_gzip("gzip"))
        self.assertTrue(_client_accepts_gzip("br, GZIP"))
        self.assertFalse(_client_accepts_gzip("br"))
        self.assertFalse(_client_accepts_gzip(None))

    def test_build_json_response_bytes_can_compress_payload(self) -> None:
        payload = {"data": "x" * 1000}
        body, headers = _build_json_response_bytes(payload, accept_encoding="gzip")

        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        decoded = gzip.decompress(body).decode("utf-8")
        self.assertEqual(json.loads(decoded)["data"], "x" * 1000)

    def test_create_fastapi_app_raises_clear_error_when_dependency_missing(self) -> None:
        with patch(
            "app.interfaces.mcp.fastapi_server.importlib.import_module",
            side_effect=ModuleNotFoundError("fastapi"),
        ):
            with self.assertRaisesRegex(RuntimeError, "FastAPI transport requires"):
                create_fastapi_app()


if __name__ == "__main__":
    unittest.main()
