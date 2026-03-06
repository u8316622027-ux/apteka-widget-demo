"""Token store implementations for cart sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen as default_urlopen

from app.domain.cart.entities import CartToken
from app.domain.cart.repository import CartTokenStore


@dataclass(slots=True)
class _TokenRecord:
    token: CartToken
    expires_at: float


class InMemoryCartTokenStore(CartTokenStore):
    """In-memory token store for local development and tests."""

    def __init__(self, *, ttl_seconds: int = 30 * 24 * 60 * 60) -> None:
        self._ttl_seconds = ttl_seconds
        self._records: dict[str, _TokenRecord] = {}

    def get_token(self, cart_session_id: str) -> CartToken | None:
        record = self._records.get(cart_session_id)
        if record is None:
            return None

        if record.expires_at < time():
            self._records.pop(cart_session_id, None)
            return None

        return record.token

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        self._records[cart_session_id] = _TokenRecord(
            token=token,
            expires_at=time() + self._ttl_seconds,
        )


class RedisCartTokenStore(CartTokenStore):
    """Redis-backed token store for shared sessions across instances."""

    def __init__(
        self, redis_client: Any, *, prefix: str = "cart:session", ttl_seconds: int = 604800
    ) -> None:
        self._redis = redis_client
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds

    def get_token(self, cart_session_id: str) -> CartToken | None:
        key = self._key(cart_session_id)
        raw = self._redis.get(key)
        if raw is None:
            return None

        if isinstance(raw, bytes):
            payload = json.loads(raw.decode("utf-8"))
        else:
            payload = json.loads(str(raw))

        access_token = str(payload.get("access_token") or "").strip()
        token_type = str(payload.get("token_type") or "Bearer").strip() or "Bearer"
        if not access_token:
            return None

        return CartToken(access_token=access_token, token_type=token_type)

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        key = self._key(cart_session_id)
        payload = json.dumps(
            {"access_token": token.access_token, "token_type": token.token_type},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self._redis.setex(key, self._ttl_seconds, payload)

    def _key(self, cart_session_id: str) -> str:
        return f"{self._prefix}:{cart_session_id}"


class UpstashRestCartTokenStore(CartTokenStore):
    """Upstash Redis REST-backed token store."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        prefix: str = "cart:session",
        ttl_seconds: int = 604800,
        timeout: float = 10.0,
        max_retries: int = 1,
        urlopen: Callable[..., Any] = default_urlopen,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds
        self._timeout = timeout
        self._max_retries = max(0, int(max_retries))
        self._urlopen = urlopen

    def get_token(self, cart_session_id: str) -> CartToken | None:
        key = quote(self._key(cart_session_id), safe="")
        request = Request(
            url=f"{self._base_url}/get/{key}",
            method="GET",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        with self._urlopen_with_retry(request) as response:
            payload = json.loads(response.read().decode("utf-8"))

        raw_value = payload.get("result")
        if not isinstance(raw_value, str) or not raw_value.strip():
            return None

        try:
            token_payload = json.loads(raw_value)
        except json.JSONDecodeError:
            return None

        if isinstance(token_payload, dict) and isinstance(token_payload.get("value"), str):
            try:
                nested_payload = json.loads(str(token_payload["value"]))
            except json.JSONDecodeError:
                nested_payload = None
            if isinstance(nested_payload, dict):
                token_payload = nested_payload

        access_token = str(token_payload.get("access_token") or "").strip()
        token_type = str(token_payload.get("token_type") or "Bearer").strip() or "Bearer"
        if not access_token:
            return None

        return CartToken(access_token=access_token, token_type=token_type)

    def set_token(self, cart_session_id: str, token: CartToken) -> None:
        key = quote(self._key(cart_session_id), safe="")
        value = json.dumps(
            {"access_token": token.access_token, "token_type": token.token_type},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request_payload = json.dumps(
            {"value": value, "ex": self._ttl_seconds},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            url=f"{self._base_url}/set/{key}",
            data=request_payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        with self._urlopen_with_retry(request):
            return

    def _key(self, cart_session_id: str) -> str:
        return f"{self._prefix}:{cart_session_id}"

    def _urlopen_with_retry(self, request: Request) -> Any:
        attempt = 0
        while True:
            try:
                return self._urlopen(request, timeout=self._timeout)
            except HTTPError as exc:
                if int(getattr(exc, "code", 0)) < 500:
                    raise
                if attempt >= self._max_retries:
                    raise
            except (URLError, TimeoutError):
                if attempt >= self._max_retries:
                    raise
            attempt += 1
