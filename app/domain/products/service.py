"""Products business rules."""

from __future__ import annotations

from app.domain.products.entities import ProductSummary
from app.domain.products.repository import ProductSearchRepository


class ProductSearchService:
    """Orchestrates product search validation and retrieval."""

    def __init__(self, repository: ProductSearchRepository) -> None:
        self._repository = repository

    def search_products(self, query: str, limit: int = 10) -> list[ProductSummary]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")
        if limit < 1:
            raise ValueError("limit must be greater than zero")
        return self._repository.search(normalized_query, limit=limit)
