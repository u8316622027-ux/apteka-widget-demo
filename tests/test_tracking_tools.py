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


if __name__ == "__main__":
    unittest.main()
