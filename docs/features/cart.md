# Feature: cart

## Goal
Обеспечить устойчивую корзину пользователя для MCP tools (`my_cart`, `add_to_my_cart`) через серверную сессию `cart_session_id` и серверное хранение токена корзины.

## User Flow
1. UI или tool передает `cart_session_id` (если уже есть).
2. Backend ищет `cart_session_id` в token-store.
3. Если не найдено, backend создает корзину в Apteka API (`GET /api/v1/front/cart`), сохраняет токен и выдает новый `cart_session_id`.
4. `my_cart` возвращает актуальный snapshot корзины.
5. `add_to_my_cart` изменяет корзину и возвращает обновленный snapshot.

## Inputs/Outputs
- `my_cart`:
  - Input:
    - `cart_session_id` (string, optional)
  - Output:
    - `cart_session_id`
    - `cart_created` (bool)
    - `count`
    - `total`
    - `items[]` (`product_id`, `quantity`)

- `add_to_my_cart`:
  - Input:
    - `product_id` (string, required)
    - `quantity` (integer, optional)
    - `cart_session_id` (string, optional)
  - Output: такой же snapshot как `my_cart`.

## Tool Behavior Rules (for AI)
- Если передан только `product_id` (без `quantity`) - добавить 1 единицу товара через `/cart/add`.
- Если передан `quantity` - это целевое (абсолютное) количество товара в корзине, а не дельта.
- Пример уменьшения: было `4`, пользователь просит `2` -> отправить `quantity=2` (не `-2`).
- Полное удаление товара: отправить `quantity=0`.

## Dependencies
- Apteka API:
  - `GET https://api.apteka.md/api/v1/front/cart` (создание корзины + токен)
  - `GET https://api.apteka.md/api/v1/front/cart` с `Authorization` (получение корзины)
  - `POST https://api.apteka.md/api/v1/front/cart/add` с `Authorization` и body `{"id":"<product_id>"}` (добавление +1)
  - `POST https://api.apteka.md/api/v1/front/cart/update` с `Authorization` и body `{"items":[{"product_id":"<product_id>","quantity":<target>}],"json":true}` (установка абсолютного количества, `0` = удалить)
- Token store:
  - In-memory (по умолчанию)
  - Upstash Redis REST (если заданы `UPSTASH_REDIS_REST_URL` и `UPSTASH_REDIS_REST_TOKEN`)
  - Redis (если задан `REDIS_URL` и установлен пакет `redis`)
  - TTL токена сессии задается через `CART_TOKEN_TTL_SECONDS` (по умолчанию 604800 сек)
  - Значения читаются из централизованных settings c поддержкой `.env` по умолчанию.

## Edge Cases
- Пустой `product_id` -> `ValueError`.
- `quantity < 0` -> `ValueError`.
- Неизвестный/просроченный `cart_session_id` -> создается новая корзина и новый `cart_session_id`.
- Если Redis недоступен или пакет `redis` не установлен, используется in-memory store.
- Если заданы переменные Upstash REST, они имеют приоритет над `REDIS_URL`.
- Дефолтный token-store инициализируется один раз на процесс (singleton), чтобы `cart_session_id` сохранялся между вызовами tool.

## Test Cases
- Unit:
  - автосоздание сессии при отсутствии `cart_session_id`;
  - повторное использование существующей сессии;
  - валидация `quantity` (`>= 0`);
  - добавление по умолчанию через `/add` при отсутствии `quantity`;
  - обновление количества через `/update` при переданном `quantity`, включая `0`.
- Integration-like:
  - проверка вызова `GET /front/cart` и парсинга `accessToken/tokenType`;
  - проверка payload для `/front/cart/add`;
  - проверка payload для `/front/cart/update`.
- Server wiring:
  - проверка делегирования `my_cart` и `add_to_my_cart` через MCP registry.

## Tech Debt / Next Improvements
- Добавить UI bootstrap endpoint для `ensure_cart_session` при первом открытии виджета.
- Добавить optimistic update + финальную сверку snapshot в UI перед checkout.
- Уточнить контракт полей cart API на реальных ответах prod/stage и расширить маппинг `items/total`.
