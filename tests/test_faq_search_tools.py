"""Tests for FAQ semantic search MCP tool."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.interfaces.mcp.tools.faq_tools import (
    OpenAIEmbeddingClient,
    SupabaseFaqSearchRepository,
    _read_env,
    faq_search,
)


class FaqSearchToolTests(unittest.TestCase):
    def test_faq_search_rejects_empty_query(self) -> None:
        with self.assertRaisesRegex(ValueError, "query must not be empty"):
            faq_search("   ")

    def test_faq_search_builds_embedding_and_calls_supabase_rpc(self) -> None:
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
        responses = [
            FakeResponse(
                json.dumps({"data": [{"embedding": [0.11, 0.22, 0.33]}]}).encode("utf-8")
            ),
            FakeResponse(
                json.dumps(
                    [
                        {"id": 10, "text": "Оформление заказа через корзину", "score": 0.91},
                        {"id": 11, "text": "График работы: 08:00-22:00", "score": 0.82},
                    ]
                ).encode("utf-8")
            ),
        ]

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
            return responses.pop(0)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-openai-key",
                "SUPABASE_URL": "https://demo.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "test-supabase-key",
                "SUPABASE_FAQ_SEARCH_RPC_FUNCTION": "match_faq_chunks",
            },
            clear=False,
        ):
            embedding_client = OpenAIEmbeddingClient(
                api_key="test-openai-key",
                dimensions=1536,
                urlopen=fake_urlopen,
            )
            repository = SupabaseFaqSearchRepository(
                base_url="https://demo.supabase.co",
                api_key="test-supabase-key",
                match_threshold=0.78,
                urlopen=fake_urlopen,
            )
            response = faq_search(
                "как оформить заказ",
                limit=2,
                embedding_client=embedding_client,
                repository=repository,
            )

        self.assertEqual(len(requests), 2)

        self.assertEqual(requests[0]["url"], "https://api.openai.com/v1/embeddings")
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(requests[0]["headers"].get("Authorization"), "Bearer test-openai-key")
        self.assertEqual(requests[0]["headers"].get("Content-type"), "application/json")
        self.assertEqual(
            json.loads(str(requests[0]["body"])),
            {"model": "text-embedding-3-small", "input": "как оформить заказ", "dimensions": 1536},
        )

        self.assertEqual(
            requests[1]["url"], "https://demo.supabase.co/rest/v1/rpc/match_faq_chunks"
        )
        self.assertEqual(requests[1]["method"], "POST")
        self.assertEqual(requests[1]["headers"].get("Authorization"), "Bearer test-supabase-key")
        self.assertEqual(requests[1]["headers"].get("Apikey"), "test-supabase-key")
        self.assertEqual(requests[1]["headers"].get("Content-type"), "application/json")
        self.assertEqual(requests[1]["headers"].get("Accept"), "application/json")
        self.assertEqual(requests[1]["headers"].get("User-agent"), "Mozilla/5.0")
        self.assertEqual(
            json.loads(str(requests[1]["body"])),
            {"query_embedding": [0.11, 0.22, 0.33], "match_count": 2, "match_threshold": 0.78},
        )

        self.assertEqual(response["query"], "как оформить заказ")
        self.assertEqual(response["count"], 2)
        self.assertEqual(response["chunks"][0]["id"], 10)

    def test_faq_search_uses_match_faq_chunks_rpc_name(self) -> None:
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
        responses = [
            FakeResponse(json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode("utf-8")),
            FakeResponse(json.dumps([]).encode("utf-8")),
        ]

        def fake_urlopen(request, timeout: float):
            requests.append({"url": request.full_url})
            return responses.pop(0)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-openai-key",
                "SUPABASE_URL": "https://demo.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "test-supabase-key",
                "SUPABASE_FAQ_SEARCH_RPC_FUNCTION": "wrong_rpc_name",
            },
            clear=False,
        ):
            embedding_client = OpenAIEmbeddingClient(
                api_key="test-openai-key",
                urlopen=fake_urlopen,
            )
            repository = SupabaseFaqSearchRepository(
                base_url="https://demo.supabase.co",
                api_key="test-supabase-key",
                urlopen=fake_urlopen,
            )
            faq_search("график работы", embedding_client=embedding_client, repository=repository)

        self.assertEqual(
            requests[1]["url"],
            "https://demo.supabase.co/rest/v1/rpc/match_faq_chunks",
        )

    def test_faq_search_uses_supabase_key_env_name(self) -> None:
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
        responses = [
            FakeResponse(json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode("utf-8")),
            FakeResponse(json.dumps([]).encode("utf-8")),
        ]

        def fake_urlopen(request, timeout: float):
            requests.append({"headers": dict(request.header_items())})
            return responses.pop(0)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-openai-key",
                "SUPABASE_URL": "https://demo.supabase.co",
                "SUPABASE_KEY": "test-supabase-key",
                "SUPABASE_SERVICE_ROLE_KEY": "",
            },
            clear=False,
        ):
            embedding_client = OpenAIEmbeddingClient(urlopen=fake_urlopen)
            repository = SupabaseFaqSearchRepository(urlopen=fake_urlopen)
            faq_search("график работы", embedding_client=embedding_client, repository=repository)

        self.assertEqual(requests[1]["headers"].get("Apikey"), "test-supabase-key")
        self.assertEqual(
            requests[1]["headers"].get("Authorization"),
            "Bearer test-supabase-key",
        )

    def test_read_env_prefers_dotenv_value_over_process_env(self) -> None:
        with patch(
            "app.interfaces.mcp.tools.faq_tools.read_env_file_value",
            return_value="from-dotenv",
        ):
            with patch(
                "app.interfaces.mcp.tools.faq_tools._read_os_env",
                return_value="from-process",
            ):
                value = _read_env("SUPABASE_KEY")

        self.assertEqual(value, "from-dotenv")

    def test_openai_embedding_client_uses_dimensions_from_env(self) -> None:
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
                    "body": request.data.decode("utf-8") if request.data else "",
                }
            )
            return FakeResponse(json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode("utf-8"))

        with patch("app.interfaces.mcp.tools.faq_tools._read_positive_int_env", return_value=1024):
            client = OpenAIEmbeddingClient(api_key="test-openai-key", urlopen=fake_urlopen)
            client.create_embedding("тест")

        self.assertEqual(requests[0]["url"], "https://api.openai.com/v1/embeddings")
        self.assertEqual(json.loads(str(requests[0]["body"]))["dimensions"], 1024)

    def test_supabase_repository_uses_default_match_settings_from_env(self) -> None:
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
            requests.append({"body": request.data.decode("utf-8") if request.data else ""})
            return FakeResponse(json.dumps([]).encode("utf-8"))

        with patch("app.interfaces.mcp.tools.faq_tools._read_positive_int_env", return_value=7):
            with patch("app.interfaces.mcp.tools.faq_tools._read_float_env", return_value=0.82):
                repository = SupabaseFaqSearchRepository(
                    base_url="https://demo.supabase.co",
                    api_key="test-supabase-key",
                    urlopen=fake_urlopen,
                )
                repository.search([0.1, 0.2, 0.3], limit=None)

        self.assertEqual(
            json.loads(str(requests[0]["body"])),
            {
                "query_embedding": [0.1, 0.2, 0.3],
                "match_count": 7,
                "match_threshold": 0.82,
            },
        )


if __name__ == "__main__":
    unittest.main()
