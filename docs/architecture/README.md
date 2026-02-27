# Architecture

## Overview
Проект построен как минимальный backend для MCP-интеграции с фокусом на инструмент `search_products`.

## Layers
- `app/domain/*`:
  - доменные сущности и сервисы (`ProductSummary`, `ProductSearchService`).
- `app/interfaces/mcp/tools/*`:
  - MCP tools и адаптеры к внешним API.
- `app/interfaces/mcp/server.py`:
  - HTTP транспорт для MCP JSON-RPC.

## MCP Server
- Endpoint: `POST /mcp`
- Healthcheck: `GET /health`
- Поддержанные методы:
  - `initialize`
  - `tools/list`
  - `tools/call`

## Registered Tools
- `search_products` (реализован)
- `add_to_my_cart` (stub)
- `checkout_order` (stub)
- `faq_search` (stub)
- `my_cart` (stub)
- `set_widget_theme` (stub)
- `track_order_status_ui` (stub)

## Search Integration
- Внешний API: `https://api.apteka.md/api/v1/front/search`
- Запрос: `POST` JSON body `{"query":"..."}`
- Ответ маппится в нормализованные карточки товаров.

## Local Run
```bash
python -m app.interfaces.mcp.server --host 0.0.0.0 --port 8000
```

## Quality Gates
Перед завершением задачи запускаются:
```bash
npx biome check --apply .
python -m ruff format .
python -m ruff check .
python -m pytest
npx playwright test
```
