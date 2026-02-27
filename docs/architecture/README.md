# Architecture

## Overview
Проект построен как минимальный backend для MCP-интеграции с фокусом на инструменты:
- `search_products`
- `track_order_status_ui`

## Layers
- `app/domain/*`:
  - доменные сущности и сервисы (`ProductSummary`, `ProductSearchService`, `OrderTrackingService`).
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
- `track_order_status_ui` (реализован)
- `add_to_my_cart` (stub)
- `checkout_order` (stub)
- `faq_search` (stub)
- `my_cart` (stub)
- `set_widget_theme` (stub)

## Search Integration
- Внешний API: `https://api.apteka.md/api/v1/front/search`
- Запрос: `POST` JSON body `{"query":"..."}`
- Ответ маппится в нормализованные карточки товаров.

## Tracking Integration
- Внешний API: `https://stage.apteka.md/api/orders-by-anything/{x}`
- Где `x` это номер телефона или номер заказа.
- Авторизация: `Authorization` берется из `APTEKA_TRACKING_AUTHORIZATION`.
- Источник токена:
  - сначала `os.environ`
  - если переменная не экспортирована, fallback в `.env`.
- Ответ нормализуется в:
  - `status` (человекочитаемое значение)
  - `status_code` (оригинальный код)
  - `status_hint` (контекстная подсказка для LLM/пользователя).

## Recent Changes (Tracking)
- Реализован backend tool `track_order_status_ui` (MCP handler + domain service + repository).
- Добавлена инструкция в описание tool:
  - для телефона нужен международный формат (код страны + номер);
  - новый заказ по номеру может быть недоступен до принятия оператором.
- Добавлена подмена статусов на пользовательские формулировки.
- Добавлены `status_hint` для безопасной интерпретации:
  - `packed` не считается готовностью к выдаче до `client_notified`.
- Добавлена авторизация из `env` и fallback чтение из `.env`.

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
