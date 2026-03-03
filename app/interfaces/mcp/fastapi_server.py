"""Optional FastAPI transport for MCP JSON-RPC endpoints."""

from __future__ import annotations

import argparse
import gzip
import importlib
import json
from typing import Any

from app.interfaces.mcp.server import (
    MAX_REQUEST_BODY_BYTES,
    MIN_GZIP_BYTES,
    _is_json_content_type,
    _resolve_http_request_id,
    _rpc_error,
    handle_jsonrpc_payload,
)


def _client_accepts_gzip(accept_encoding: str | None) -> bool:
    if accept_encoding is None:
        return False
    return "gzip" in accept_encoding.lower()


def _build_json_response_bytes(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    accept_encoding: str | None,
) -> tuple[bytes, dict[str, str]]:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) < MIN_GZIP_BYTES or not _client_accepts_gzip(accept_encoding):
        return encoded, {}

    compressed = gzip.compress(encoded, compresslevel=5)
    return compressed, {"Content-Encoding": "gzip", "Vary": "Accept-Encoding"}


def create_fastapi_app(*, registry: dict[str, Any] | None = None) -> Any:
    try:
        fastapi = importlib.import_module("fastapi")
        responses = importlib.import_module("fastapi.responses")
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "FastAPI transport requires optional dependencies: fastapi and uvicorn."
        ) from exc

    app = fastapi.FastAPI(title="Apteka MCP", version="0.1.0")
    Response = responses.Response
    JSONResponse = responses.JSONResponse

    @app.get("/health")
    async def health(request: Any) -> Any:
        request_id = _resolve_http_request_id(request.headers.get("x-request-id"))
        return JSONResponse({"status": "ok"}, headers={"X-Request-Id": request_id})

    @app.post("/mcp")
    async def mcp_rpc(request: Any) -> Any:
        request_id = _resolve_http_request_id(request.headers.get("x-request-id"))
        content_type = request.headers.get("content-type")
        if not _is_json_content_type(content_type):
            return JSONResponse(
                _rpc_error(None, -32600, "Invalid Request: Content-Type must be application/json"),
                status_code=415,
                headers={"X-Request-Id": request_id},
            )

        raw_body = await request.body()
        if len(raw_body) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                _rpc_error(None, -32600, "Invalid Request: body is too large"),
                status_code=413,
                headers={"X-Request-Id": request_id},
            )

        try:
            request_payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            return JSONResponse(
                _rpc_error(None, -32700, "Parse error"),
                status_code=400,
                headers={"X-Request-Id": request_id},
            )

        response_payload = handle_jsonrpc_payload(
            request_payload,
            registry=registry,
            http_request_id=request_id,
        )
        if response_payload is None:
            return Response(status_code=204, headers={"X-Request-Id": request_id})

        response_bytes, encoding_headers = _build_json_response_bytes(
            response_payload,
            accept_encoding=request.headers.get("accept-encoding"),
        )
        headers = {"X-Request-Id": request_id}
        headers.update(encoding_headers)
        return Response(
            content=response_bytes,
            status_code=200,
            media_type="application/json",
            headers=headers,
        )

    return app


def run_fastapi_server(host: str = "127.0.0.1", port: int = 8001) -> None:
    try:
        uvicorn = importlib.import_module("uvicorn")
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("FastAPI transport requires optional dependency: uvicorn.") from exc

    app = create_fastapi_app()
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FastAPI MCP transport.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    run_fastapi_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
