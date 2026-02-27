# Feature: products

## Goal
Отдавать нормализованную карточку товара для интерфейса и MCP tools.

## User Flow
1. Поиск возвращает список карточек `products[]`.
2. Клиент использует поля карточки для рендера списка.

## Inputs/Outputs
- Inputs:
  - Данные от внешнего API аптеки.
- Outputs:
  - Поля карточки:
    - `id`
    - `name_ro`
    - `name_ru`
    - `manufacturer`
    - `internationalName`
    - `country`
    - `price`
    - `discount_price`
    - `description_ro`
    - `description_ru`
    - `image_url`

## Dependencies
- Маппинг в `app/interfaces/mcp/tools/search_tools.py`.
- Сущность `ProductSummary` в `app/domain/products/entities.py`.

## Edge Cases
- Частично заполненные данные от внешнего API.
- Отсутствие изображений и переводов.

## Test Cases
- Unit:
  - корректная сборка `ProductSummary`.
- Integration-like:
  - маппинг сложного payload `translations/images/price`.
- E2E:
  - проверка отображения карточек в UI (пока не реализовано).

## Tech Debt / Next Improvements
- Уточнить обязательные/необязательные поля карточки.
- Добавить схемную валидацию ответа перед отправкой в клиент.
