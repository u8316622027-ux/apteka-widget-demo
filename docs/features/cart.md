# Feature: cart

## Goal
Обеспечить устойчивую корзину пользователя для UI и MCP tools (`my_cart`, `add_to_my_cart`) через серверную сессию `cart_session_id` и серверное хранение токена корзины.

## User Flow
1. UI или tool передает `cart_session_id` (если уже есть).
2. Backend ищет `cart_session_id` в token-store.
3. Если не найдено, backend создает корзину в Apteka API (`GET /api/v1/front/cart`), сохраняет токен и выдает новый `cart_session_id`.
4. `my_cart` возвращает актуальный snapshot корзины.
5. `add_to_my_cart` добавляет товар и возвращает обновленный snapshot.

## Inputs/Outputs
- `my_cart`:
  - Input: `cart_session_id` (string, optional)
  - Output:
    - `cart_session_id`
    - `cart_created` (bool)
    - `count`
    - `total`
    - `items[]` (`product_id`, `quantity`)

- `add_to_my_cart`:
  - Input:
    - `product_id` (string, required)
    - `quantity` (integer, optional, default 1)
    - `cart_session_id` (string, optional)
  - Output: такой же snapshot как `my_cart`.

## Dependencies
- Apteka API:
  - `GET https://api.apteka.md/api/v1/front/cart` (создание корзины + токен)
  - `GET https://api.apteka.md/api/v1/front/cart` с `Authorization` (получение корзины)
  - `POST https://api.apteka.md/api/v1/front/cart/items` с `Authorization` (добавление товара)
- Token store:
  - In-memory (по умолчанию)
  - Redis (если задан `REDIS_URL` и установлен пакет `redis`)

## Edge Cases
- Пустой `product_id` -> `ValueError`.
- `quantity < 1` -> `ValueError`.
- Неизвестный/просроченный `cart_session_id` -> создается новая корзина и новый `cart_session_id`.
- Если Redis недоступен или пакет `redis` не установлен, используется in-memory store.

## Test Cases
- Unit:
  - автосоздание сессии при отсутствии `cart_session_id`;
  - повторное использование существующей сессии;
  - валидация `quantity`.
- Integration-like:
  - проверка вызова `GET /front/cart` и парсинга `accessToken/tokenType`.
- Server wiring:
  - проверка делегирования `my_cart` и `add_to_my_cart` через MCP registry.

## Tech Debt / Next Improvements
- Добавить UI bootstrap endpoint для `ensure_cart_session` при первом открытии виджета.
- Добавить optimistic update + финальную сверку snapshot в UI перед checkout.
- Уточнить контракт полей cart API на реальных ответах prod/stage и расширить маппинг items/total.
