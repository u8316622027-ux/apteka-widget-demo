"""Tests for the search products backend flow."""

from __future__ import annotations

import unittest

from app.domain.products.entities import ProductSummary
from app.domain.products.service import ProductSearchService
from app.interfaces.mcp.tools.search_tools import AptekaSearchRepository, search_products


class InMemoryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None]] = []

    def search(self, query: str, limit: int | None = None) -> list[ProductSummary]:
        self.calls.append((query, limit))
        return [
            ProductSummary(
                id="p-1",
                name_ro="Ibuprofen 200mg",
                name_ru="Ibuprofen 200mg RU",
                manufacturer="Pharma Inc",
                international_name="Ibuprofenum",
                country="Germany",
                price=49.5,
                discount_price=39.5,
                description_ro="Descriere RO",
                description_ru="Описание RU",
                image_url=None,
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
                    id="p-1",
                    name_ro="Ibuprofen 200mg",
                    name_ru="Ibuprofen 200mg RU",
                    manufacturer="Pharma Inc",
                    international_name="Ibuprofenum",
                    country="Germany",
                    price=49.5,
                    discount_price=39.5,
                    description_ro="Descriere RO",
                    description_ru="Описание RU",
                    image_url=None,
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

        requests: list[dict[str, object]] = []

        def fake_urlopen(request, timeout: float):
            requests.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "headers": dict(request.header_items()),
                    "body": request.data.decode("utf-8") if request.data else "",
                    "timeout": timeout,
                }
            )
            payload = (
                '{"categories":[],"items":['
                '{"id":"A12","name":"Nurofen","price":39.9,"discountPrice":32.9,'
                '"manufacturer":"Reckitt","internationalName":"Ibuprofenum","country":"UK",'
                '"translations":{"ro":{"name":"Nurofen RO","description":"Descriere Nurofen"},'
                '"ru":{"name":"Nurofen RU","description":"Описание Нурофен"}},'
                '"meta":{"image":"https://img.local/nurofen.jpg"},'
                '"url":"https://apteka.md/nurofen"},'
                '{"id":"A13","name":"Citramon","price":12.0,'
                '"manufacturer":"LUBNIFARM","internationalName":"Acidum acetylsalicylicum","country":"Ukraine",'
                '"translations":{"ro":{"name":"Citramon RO","description":"Descriere Citramon"},'
                '"ru":{"name":"Citramon RU","description":"Описание Цитрамон"}},'
                '"image":"https://img.local/citramon.jpg",'
                '"url":"https://apteka.md/citramon"}],"stores":[]}'
            ).encode("utf-8")
            return FakeResponse(payload)

        repository = AptekaSearchRepository(urlopen=fake_urlopen)

        response = search_products("nurofen", repository=repository, limit=1)

        self.assertTrue(requests)
        self.assertEqual(requests[0]["url"], "https://stage.apteka.md/api/v1/front/search")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(requests[0]["body"], '{"query":"nurofen"}')
        self.assertEqual(requests[0]["headers"].get("Content-type"), "application/json")
        self.assertNotIn("Authorization", requests[0]["headers"])
        self.assertEqual(response["count"], 2)
        self.assertEqual(
            response["products"],
            [
                {
                    "id": "A12",
                    "name_ro": "Nurofen RO",
                    "name_ru": "Nurofen RU",
                    "manufacturer": "Reckitt",
                    "internationalName": "Ibuprofenum",
                    "country": "UK",
                    "price": 39.9,
                    "discount_price": 32.9,
                    "description_ro": "Descriere Nurofen",
                    "description_ru": "Описание Нурофен",
                    "image_url": "https://img.local/nurofen.jpg",
                },
                {
                    "id": "A13",
                    "name_ro": "Citramon RO",
                    "name_ru": "Citramon RU",
                    "manufacturer": "LUBNIFARM",
                    "internationalName": "Acidum acetylsalicylicum",
                    "country": "Ukraine",
                    "price": 12.0,
                    "discount_price": None,
                    "description_ro": "Descriere Citramon",
                    "description_ru": "Описание Цитрамон",
                    "image_url": "https://img.local/citramon.jpg",
                },
            ],
        )
        self.assertNotIn("name", response["products"][0])
        self.assertNotIn("product_url", response["products"][0])

    def test_search_products_extracts_image_from_images_full(self) -> None:
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
            payload = (
                '{"items":[{"id":"X1","price":10,'
                '"translations":{"ro":{"name":"Produs RO"},"ru":{"name":"Товар RU"}},'
                '"images":[{"id":1,"preview":"https://api.apteka.md/media/1/preview.webp",'
                '"full":"https://api.apteka.md/media/1/full.webp"}]}]}'
            ).encode("utf-8")
            return FakeResponse(payload)

        repository = AptekaSearchRepository(urlopen=fake_urlopen)
        response = search_products("produs", repository=repository)

        self.assertEqual(response["count"], 1)
        self.assertEqual(
            response["products"][0]["image_url"], "https://api.apteka.md/media/1/full.webp"
        )
