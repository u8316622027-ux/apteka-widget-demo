# Architecture

## Overview
Проект построен как backend для MCP-интеграции с реализованными инструментами поиска, трекинга заказа и корзины.

## Layers
- `app/domain/*`:
  - доменные сущности и сервисы (`ProductSearchService`, `CartService`, tracking-domain logic).
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
- `add_to_my_cart` (реализован)
- `checkout_order` (stub)
- `faq_search` (stub)
- `my_cart` (реализован)
- `set_widget_theme` (stub)
- `track_order_status_ui` (реализован)

## Search Integration
- Внешний API: `https://api.apteka.md/api/v1/front/search`
- Запрос: `POST` JSON body `{"query":"..."}`
- Ответ маппится в нормализованные карточки товаров.

## Cart Integration
- Создание корзины: `GET https://api.apteka.md/api/v1/front/cart`.
- Добавление товара: `POST https://api.apteka.md/api/v1/front/cart/add` с body `{"id":"<product_id>"}`.
- Чтение корзины: `GET https://api.apteka.md/api/v1/front/cart` с `Authorization: Bearer <accessToken>`.
- Токен корзины хранится серверно через `CartTokenStore`:
  - `InMemoryCartTokenStore` (fallback),
  - `UpstashRestCartTokenStore` (`UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`),
  - `RedisCartTokenStore` (`REDIS_URL`).

## Tracking Integration
- Внешний API: `https://stage.apteka.md/api/orders-by-anything/{lookup}`.
- Заголовок авторизации берется из `APTEKA_TRACKING_AUTHORIZATION`.
- Tool возвращает нормализованный статус + `status_hint`.

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
