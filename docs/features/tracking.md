# Feature: tracking

## Goal
Дать пользователю возможность проверить статус заказа через tool `track_order_status_ui` по номеру заказа или телефону.

## User Flow
1. Клиент вызывает MCP `tools/call` с `name=track_order_status_ui`.
2. В `arguments.lookup` передается номер заказа или номер телефона.
3. Сервер обращается в stage API `orders-by-anything/{lookup}`.
4. Сервер возвращает найденные заказы в `structuredContent`.

## Inputs/Outputs
- Inputs:
  - `lookup` (string, обязательный):
    - номер заказа, или
    - телефон в международном формате: сначала код страны, затем номер.
- Outputs:
  - `lookup`
  - `count`
  - `orders[]`

## Dependencies
- Внешний API: `https://stage.apteka.md/api/orders-by-anything/{x}`
- Где `x` это номер телефона или номер заказа.

## Edge Cases
- Пустой `lookup` -> `ValueError`.
- Если API вернул неожиданный формат, `orders = []`.

## Test Cases
- Unit:
  - валидация пустого `lookup`;
  - проверка регистрации описания tool с указанием формата телефона.
- Integration-like:
  - проверка GET запроса в stage API;
  - проверка нормализации ответа в `orders[]`.
- E2E:
  - smoke `playwright` (placeholder).

## Tech Debt / Next Improvements
- Добавить нормализацию/схему для `orders[]` под UI-контракт.
- Добавить retries/backoff и обработку 4xx/5xx с пользовательскими сообщениями.
