"""Tests for order tracking tool backend flow."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.interfaces.mcp.tools.tracking_tools import (
    AptekaOrderTrackingRepository,
    track_order_status_ui,
)


class OrderTrackingTests(unittest.TestCase):
    def test_track_order_status_ui_rejects_empty_lookup(self) -> None:
        with self.assertRaisesRegex(ValueError, "lookup must not be empty"):
            track_order_status_ui("   ")

    def test_track_order_status_ui_calls_stage_api_and_returns_orders(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[dict[str, object]] = []

        def fake_urlopen(request, timeout: float):
            requests.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "headers": dict(request.header_items()),
                    "timeout": timeout,
                }
            )
            payload = (
                '{"data":[{"order_number":"ORD-123","status":"pending"}],"meta":{"source":"stage"}}'
            ).encode("utf-8")
            return FakeResponse(payload)

        with patch.dict(os.environ, {"APTEKA_TRACKING_AUTHORIZATION": "Bearer test-token"}):
            repository = AptekaOrderTrackingRepository(urlopen=fake_urlopen)
            response = track_order_status_ui("37369111222", repository=repository)

        self.assertTrue(requests)
        self.assertEqual(
            requests[0]["url"], "https://stage.apteka.md/api/orders-by-anything/37369111222"
        )
        self.assertEqual(requests[0]["method"], "GET")
        self.assertEqual(requests[0]["headers"].get("Authorization"), "Bearer test-token")
        self.assertEqual(response["lookup"], "37369111222")
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["orders"][0]["order_number"], "ORD-123")
        self.assertEqual(response["orders"][0]["status"], "заказ получен")
        self.assertEqual(response["orders"][0]["status_code"], "pending")
        self.assertIn("оператор", response["orders"][0]["status_hint"].lower())

    def test_track_order_status_ui_maps_new_status(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        def fake_urlopen(request, timeout: float):
            payload = '[{"order_number":"ORD-NEW","status":"NEW"}]'.encode("utf-8")
            return FakeResponse(payload)

        repository = AptekaOrderTrackingRepository(urlopen=fake_urlopen, authorization="Bearer test")
        response = track_order_status_ui("ORD-NEW", repository=repository)

        self.assertEqual(response["count"], 1)
        self.assertEqual(response["orders"][0]["status"], "только создан, ожидание обработки")
        self.assertEqual(response["orders"][0]["status_code"], "NEW")
        self.assertIn("подожд", response["orders"][0]["status_hint"].lower())

    def test_track_order_status_ui_maps_packed_status_with_non_ready_hint(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        def fake_urlopen(request, timeout: float):
            payload = '[{"order_number":"ORD-PACK","status":"packed"}]'.encode("utf-8")
            return FakeResponse(payload)

        repository = AptekaOrderTrackingRepository(urlopen=fake_urlopen, authorization="Bearer test")
        response = track_order_status_ui("ORD-PACK", repository=repository)

        self.assertEqual(response["orders"][0]["status"], "заказ собран")
        self.assertEqual(response["orders"][0]["status_code"], "packed")
        self.assertIn("не готов", response["orders"][0]["status_hint"].lower())

    def test_repository_uses_dotenv_token_when_os_env_is_empty(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[dict[str, object]] = []

        def fake_urlopen(request, timeout: float):
            requests.append({"headers": dict(request.header_items())})
            return FakeResponse(b"[]")

        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "app.interfaces.mcp.tools.tracking_tools.read_env_file_value",
                return_value="Bearer from-dotenv",
            ):
                repository = AptekaOrderTrackingRepository(urlopen=fake_urlopen)
                repository.lookup("ORD-1")

        self.assertEqual(requests[0]["headers"].get("Authorization"), "Bearer from-dotenv")

    def test_repository_uses_apteka_base_url_from_env(self) -> None:
        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc_val, exc_tb) -> None:
                return None

        requests: list[str] = []

        def fake_urlopen(request, timeout: float):
            del timeout
            requests.append(request.full_url)
            return FakeResponse(b"[]")

        with patch.dict(os.environ, {"APTEKA_BASE_URL": "https://prod.apteka.md"}, clear=False):
            repository = AptekaOrderTrackingRepository(urlopen=fake_urlopen, authorization="Bearer test")
            repository.lookup("ORD-1")

        self.assertEqual(requests, ["https://prod.apteka.md/api/orders-by-anything/ORD-1"])


if __name__ == "__main__":
    unittest.main()
