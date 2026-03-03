# Архитектура

## Обзор
Проект представляет собой MCP backend с рабочими tool-адаптерами для:
- `search_products`
- `add_to_my_cart`
- `my_cart`
- `track_order_status_ui`
- `checkout_order`
- `support_knowledge_search`

## Слои
- `app/domain/*`:
  - доменные сущности и сервисы (`ProductSearchService`, `CartService`, `OrderTrackingService`, `FaqSearchService`)
- `app/core/config.py`:
  - централизованные runtime-настройки (env + `.env`)
- `app/interfaces/mcp/tools/*`:
  - MCP tools и адаптеры к внешним API
- `app/interfaces/mcp/server.py`:
  - HTTP JSON-RPC транспорт на `http.server`
- `app/interfaces/mcp/fastapi_server.py`:
  - optional FastAPI транспорт с async offload JSON-RPC dispatch

## MCP Transport Endpoints
- Основной RPC endpoint: `POST /mcp`
- Healthcheck: `GET /health`
- Runtime metrics: `GET /metrics`

## HTTP Correlation
- Каждый HTTP-ответ содержит `X-Request-Id`.
- Если входящий `X-Request-Id` передан клиентом, он переиспользуется.
- Если не передан, сервер генерирует новый request id.
- `http_request_id` прокидывается в обработку JSON-RPC и в structured error payload для корреляции логов.

## JSON-RPC методы
- `initialize`
- `tools/list`
- `tools/call`

## Зарегистрированные Tools
- `search_products` (реализован)
- `add_to_my_cart` (реализован: single add + batch update merge)
- `my_cart` (реализован)
- `track_order_status_ui` (реализован)
- `checkout_order` (implemented)
- `support_knowledge_search` (implemented: OpenAI embeddings + Supabase vector RPC)
- `set_widget_theme` (stub)

## Runtime Metrics
`GET /metrics` возвращает snapshot:
- `rpc_requests_total`
- `tool_calls_total`
- `tool_errors_total`
- `cache_hits_total`
- `cache_misses_total`
- `tools.<tool_name>.calls/errors/avg_latency_ms`

## Cache
- TTL cache применяется к:
  - `search_products`
  - `track_order_status_ui`
- Конфигурация через `app/core/config.py`:
  - `MCP_SEARCH_CACHE_TTL_SECONDS`
  - `MCP_TRACKING_CACHE_TTL_SECONDS`
  - `MCP_TOOL_CACHE_MAX_ENTRIES`

## Внешние API
- Базовый URL для Apteka API задается через env (`APTEKA_BASE_URL`) и используется всеми tool-адаптерами.
- Поиск:
  - `{APTEKA_BASE_URL}/api/v1/front/search`
- Корзина:
  - `{APTEKA_BASE_URL}/api/v1/front/cart`
  - `{APTEKA_BASE_URL}/api/v1/front/cart/update`
- Checkout reference:
  - `{APTEKA_BASE_URL}/api/v1/front//regions`
  - `{APTEKA_BASE_URL}/api/v1/front//cities-without-regions`
  - `{APTEKA_BASE_URL}/api/v1/front//pharmacies/new-list`
  - `{APTEKA_BASE_URL}/api/v1/front/delivery/calculate/pick-up/{pharmacy_id}`
  - `{APTEKA_BASE_URL}/api/v1/front/order/confirm-order-by-using-mobile`
- Трекинг заказа:
  - `{APTEKA_BASE_URL}/api/orders-by-anything/{x}`

## Локальный запуск
```bash
python -m app.interfaces.mcp.server --host 0.0.0.0 --port 8000
python -m app.interfaces.mcp.fastapi_server --host 0.0.0.0 --port 8001
```

## Quality Gates
```bash
npx biome check --apply .
python -m ruff format .
python -m ruff check .
python -m pytest
npx playwright test
```
