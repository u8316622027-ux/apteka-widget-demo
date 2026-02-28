# Архитектура

## Обзор
Проект представляет собой минимальный MCP backend с рабочими tool-адаптерами для:
- `search_products`
- `add_to_my_cart`
- `my_cart`
- `track_order_status_ui`

## Слои
- `app/domain/*`:
  - доменные сущности и сервисы (`ProductSearchService`, `CartService`, `OrderTrackingService`)
- `app/core/config.py`:
  - централизованные runtime-настройки (env + `.env`)
- `app/interfaces/mcp/tools/*`:
  - MCP tools и адаптеры к внешним API
- `app/interfaces/mcp/server.py`:
  - HTTP JSON-RPC транспорт MCP

## MCP Server
- Endpoint: `POST /mcp`
- Healthcheck: `GET /health`
- Методы:
  - `initialize`
  - `tools/list`
  - `tools/call`

## Зарегистрированные Tools
- `search_products` (реализован)
- `add_to_my_cart` (реализован: single add + batch update merge)
- `my_cart` (реализован)
- `track_order_status_ui` (реализован)
- `checkout_order` (stub)
- `support_knowledge_search` (implemented: OpenAI embeddings + Supabase vector RPC)
- `set_widget_theme` (stub)

## Внешние API
- Поиск:
  - `https://stage.apteka.md/api/v1/front/search`
- Корзина:
  - `https://stage.apteka.md/api/v1/front/cart`
  - `https://stage.apteka.md/api/v1/front/cart/add`
  - `https://stage.apteka.md/api/v1/front/cart/update`
- Трекинг заказа:
  - `https://stage.apteka.md/api/orders-by-anything/{x}`

## Локальный запуск
```bash
python -m app.interfaces.mcp.server --host 0.0.0.0 --port 8000
```

## Quality Gates
```bash
npx biome check --apply .
python -m ruff format .
python -m ruff check .
python -m pytest
npx playwright test
```
