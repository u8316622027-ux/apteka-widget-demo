# Feature: checkout

## Goal
Запустить первый шаг оформления заказа через tool `checkout_order` на основе текущей корзины пользователя.

## User Flow
1. Клиент вызывает MCP `tools/call` с `name=checkout_order`.
2. Backend проверяет корзину пользователя по `cart_session_id`:
   - если корзина пустая, возвращает дружелюбное сообщение с просьбой добавить товары;
   - если корзина не пустая, продолжает flow checkout.
3. При первом успешном вызове checkout backend загружает справочные данные (и кеширует в памяти процесса):
   - `GET https://stage.apteka.md/api/v1/front//regions`
   - `GET https://stage.apteka.md/api/v1/front//cities-without-regions`
   - `GET https://stage.apteka.md/api/v1/front//pharmacies/new-list`
4. Backend возвращает шаг выбора типа доставки:
   - `Самовывоз`: бесплатная доставка в аптеки по всей стране.
   - `Курьерская доставка`: доставка по Молдове курьерской службой.

## Inputs/Outputs
- Inputs:
  - `cart_session_id` (string, optional)
- Outputs:
  - `status`:
    - `cart_empty` для пустой корзины;
    - `delivery_method_selection` при переходе к checkout.
  - `cart_session_id`
  - `message` (для `cart_empty`)
  - `cart_count`, `cart_total` (для `delivery_method_selection`)
  - `delivery_options[]` (для `delivery_method_selection`)
  - `reference_data_meta` (counts по загруженным справочникам)

## Dependencies
- Cart tools infrastructure:
  - `my_cart` (reuse текущей сессии и snapshot корзины)
- External checkout reference API:
  - `/regions` (GET)
  - `/cities-without-regions` (GET)
  - `/pharmacies/new-list` (GET)

## Edge Cases
- Если `cart_session_id` отсутствует или невалиден, создается новая сессия корзины.
- Если после проверки корзина пустая, справочные checkout-данные не запрашиваются.
- Справочные данные кешируются в памяти процесса для снижения повторной нагрузки на API.

## Test Cases
- Unit:
  - `checkout_order` возвращает `cart_empty` и user-friendly сообщение, если корзина пустая.
  - `checkout_order` при непустой корзине возвращает шаг `delivery_method_selection`.
  - `checkout_order` использует кеш справочных данных между вызовами.
  - репозиторий checkout вызывает все 3 endpoint как `GET`.
- Server wiring:
  - MCP `tools/call` с `checkout_order` делегируется в `checkout_order` tool handler.

## Next Steps
- Реализовать следующий шаг для каждой опции доставки:
  - сценарий `pickup`;
  - сценарий `courier_delivery`.
