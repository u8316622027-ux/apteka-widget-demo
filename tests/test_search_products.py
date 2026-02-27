"""Tests for the search products backend flow."""

from __future__ import annotations

from dataclasses import asdict
import unittest

from app.domain.products.entities import ProductSummary
from app.domain.products.service import ProductSearchService
from app.interfaces.mcp.tools.search_tools import AptekaSearchRepository, search_products


class InMemoryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int = 10) -> list[ProductSummary]:
        self.calls.append((query, limit))
        return [
            ProductSummary(
                product_id="p-1",
                name="Ibuprofen 200mg",
                price=49.5,
                image_url=None,
                product_url=None,
            )
        ]


class ProductSearchTests(unittest.TestCase):
    def test_product_search_service_trims_query_and_passes_limit(self) -> None:
        repository = InMemoryRepository()
        service = ProductSearchService(repository)

        result = service.search_products("  ibu  ", limit=5)

        self.assertEqual(repository.calls, [("ibu", 5)])
        self.assertEqual(
            result,
            [
                ProductSummary(
                    product_id="p-1",
                    name="Ibuprofen 200mg",
                    price=49.5,
                    image_url=None,
                    product_url=None,
                )
            ],
        )

    def test_product_search_service_rejects_empty_query(self) -> None:
        repository = InMemoryRepository()
        service = ProductSearchService(repository)

        with self.assertRaisesRegex(ValueError, "query must not be empty"):
            service.search_products("   ")

    def test_search_products_maps_external_api_payload(self) -> None:
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
            requests.append(request.full_url)
            payload = (
                b'{"results":[{"id":"A12","name":"Nurofen","price":39.9,'
                b'"image":"https://img.local/nurofen.jpg","url":"https://apteka.md/nurofen"}]}'
            )
            return FakeResponse(payload)

        repository = AptekaSearchRepository(urlopen=fake_urlopen)

        response = search_products("nurofen", repository=repository, limit=3)

        self.assertTrue(requests)
        self.assertIn("query=nurofen", requests[0])
        self.assertIn("limit=3", requests[0])
        self.assertEqual(response["count"], 1)
        self.assertEqual(
            response["products"],
            [
                asdict(
                    ProductSummary(
                        product_id="A12",
                        name="Nurofen",
                        price=39.9,
                        image_url="https://img.local/nurofen.jpg",
                        product_url="https://apteka.md/nurofen",
                    )
                )
            ],
        )
