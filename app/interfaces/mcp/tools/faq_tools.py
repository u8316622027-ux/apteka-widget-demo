"""MCP FAQ tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen as default_urlopen

from app.domain.faq.repository import FaqSearchRepository
from app.domain.faq.service import FaqSearchService

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
OPENAI_EMBEDDINGS_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDINGS_DIMENSIONS = 1536


class OpenAIEmbeddingClient:
    """HTTP client for OpenAI embeddings API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._api_key = (api_key or _read_env("OPENAI_API_KEY")).strip()
        self._timeout = timeout
        self._urlopen = urlopen

    def create_embedding(self, text: str) -> list[float]:
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        payload = json.dumps(
            {
                "model": OPENAI_EMBEDDINGS_MODEL,
                "input": text,
                "dimensions": OPENAI_EMBEDDINGS_DIMENSIONS,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=OPENAI_EMBEDDINGS_URL,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with self._urlopen(request, timeout=self._timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

        data = response_payload.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("OpenAI embeddings response is missing data")
        first_item = data[0] if isinstance(data[0], dict) else {}
        embedding = first_item.get("embedding") if isinstance(first_item, dict) else None
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("OpenAI embeddings response is missing embedding")
        return [float(value) for value in embedding]


class SupabaseFaqSearchRepository(FaqSearchRepository):
    """Supabase RPC-backed FAQ semantic search repository."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        rpc_function: str | None = None,
        timeout: float = 10.0,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = (base_url or _read_env("SUPABASE_URL")).strip().rstrip("/")
        self._api_key = (api_key or _read_env("SUPABASE_SERVICE_ROLE_KEY")).strip()
        self._rpc_function = (
            rpc_function or _read_env("SUPABASE_FAQ_SEARCH_RPC_FUNCTION") or "match_faq_chunks"
        ).strip()
        self._timeout = timeout
        self._urlopen = urlopen

    def search(self, query_embedding: list[float], limit: int | None = None) -> list[dict[str, Any]]:
        if not self._base_url:
            raise ValueError("SUPABASE_URL is not configured")
        if not self._api_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is not configured")
        if not self._rpc_function:
            raise ValueError("SUPABASE_FAQ_SEARCH_RPC_FUNCTION is not configured")

        effective_limit = limit if limit is not None else 5
        payload = json.dumps(
            {
                "query_embedding": query_embedding,
                "match_count": effective_limit,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=f"{self._base_url}/rest/v1/rpc/{self._rpc_function}",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "apikey": self._api_key,
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with self._urlopen(request, timeout=self._timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

        if not isinstance(response_payload, list):
            return []
        return [chunk for chunk in response_payload if isinstance(chunk, dict)]


def faq_search(
    query: str,
    *,
    limit: int | None = None,
    embedding_client: OpenAIEmbeddingClient | None = None,
    repository: FaqSearchRepository | None = None,
) -> dict[str, Any]:
    """Tool entrypoint for semantic FAQ search."""

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")

    effective_embedding_client = embedding_client or OpenAIEmbeddingClient()
    query_embedding = effective_embedding_client.create_embedding(normalized_query)

    effective_repository = repository or SupabaseFaqSearchRepository()
    service = FaqSearchService(effective_repository)
    normalized_query, chunks = service.search(normalized_query, query_embedding, limit=limit)
    return {
        "query": normalized_query,
        "count": len(chunks),
        "chunks": chunks,
    }


def _read_env(key: str) -> str:
    value = _read_os_env(key).strip()
    if value:
        return value
    return _read_env_file_value(key)


def _read_os_env(key: str) -> str:
    import os

    return str(os.getenv(key, "")).strip()


def _read_env_file_value(key: str) -> str:
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if not env_path.exists():
        return ""

    prefix = f"{key}="
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(prefix):
            continue
        value = line[len(prefix) :].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value.strip()

    return ""
