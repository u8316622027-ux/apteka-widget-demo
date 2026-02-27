# Feature: search

## Goal
Дать пользователю поиск лекарств в каталоге через tool `search_products`, доступный из MCP.

## User Flow
1. Клиент вызывает MCP `tools/call` c `name=search_products`.
2. Сервер валидирует `query` и вызывает API аптеки.
3. Сервер возвращает нормализованный список товаров в `structuredContent`.

## Inputs/Outputs
- Inputs:
  - `query` (string, обязательный)
  - `limit` (integer, опционально; сейчас не ограничивает выдачу)
- Outputs:
  - `query`
  - `count`
  - `products[]` со структурой:
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
- Внешний API: `https://api.apteka.md/api/v1/front/search`
- Метод: `POST`
- Body: `{"query":"..."}`
- Токен не используется.

## Edge Cases
- Пустой `query` -> `ValueError`.
- Если нет `translations`, `name_ro/name_ru` заполняются из базового имени.
- Если нет полей изображений, `image_url = null`.
- Если нет скидки, `discount_price = null`.

## Test Cases
- Unit:
  - валидация пустого `query`;
  - передача `query`/`limit` через сервис.
- Integration-like:
  - проверка `POST` запроса в API;
  - проверка маппинга полей товара;
  - извлечение изображения из `images[].full`.
- E2E:
  - smoke `playwright` (placeholder).

## Tech Debt / Next Improvements
- Реализовать реальный смысл параметра `limit` (сейчас фактически не режет выдачу).
- Добавить пагинацию/курсоры, если API поддерживает.
- Добавить трекинг rate-limit headers из ответа API.
