"""MCP search tools."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen as default_urlopen

from app.domain.products.entities import ProductSummary
from app.domain.products.repository import ProductSearchRepository
from app.domain.products.service import ProductSearchService

APTEKA_SEARCH_URL = "https://api.apteka.md/api/v1/front/search"


class AptekaSearchRepository(ProductSearchRepository):
    """HTTP-backed repository for apteka product search."""

    def __init__(
        self,
        *,
        base_url: str = APTEKA_SEARCH_URL,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = base_url
        self._timeout = timeout
        self._urlopen = urlopen

    def search(self, query: str, limit: int = 10) -> list[ProductSummary]:
        query_string = urlencode({"query": query, "limit": limit})
        request = Request(url=f"{self._base_url}?{query_string}", method="GET")
        with self._urlopen(request, timeout=self._timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        items = _extract_items(payload)
        return [_map_product(item) for item in items]


def search_products(
    query: str,
    *,
    limit: int = 10,
    repository: ProductSearchRepository | None = None,
) -> dict[str, Any]:
    """Tool entrypoint for product search."""

    effective_repository = repository or AptekaSearchRepository()
    service = ProductSearchService(effective_repository)
    products = service.search_products(query, limit=limit)
    return {
        "query": query.strip(),
        "count": len(products),
        "products": [asdict(product) for product in products],
    }


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "products"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("results", "items", "products"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def _map_product(item: dict[str, Any]) -> ProductSummary:
    product_id = str(item.get("id") or item.get("product_id") or item.get("sku") or "")
    name = str(item.get("name") or item.get("title") or "")

    raw_price = item.get("price")
    price: float | None
    if raw_price is None:
        price = None
    else:
        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            price = None

    image_url = item.get("image") or item.get("image_url")
    product_url = item.get("url") or item.get("product_url")

    return ProductSummary(
        product_id=product_id,
        name=name,
        price=price,
        image_url=str(image_url) if image_url else None,
        product_url=str(product_url) if product_url else None,
    )
