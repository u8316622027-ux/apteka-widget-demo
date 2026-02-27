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
  - `orders[]`:
    - `status` (понятный пользователю текст)
    - `status_code` (исходный код статуса от API)
    - `status_hint` (контекстная подсказка по статусу для корректного ответа ИИ)

## Dependencies
- Внешний API: `https://stage.apteka.md/api/orders-by-anything/{x}`
- Где `x` это номер телефона или номер заказа.
- Заголовок авторизации берется из `APTEKA_TRACKING_AUTHORIZATION`.
- Источник токена:
  - сначала `os.environ`,
  - затем fallback чтение из `.env`.

## Status Mapping
- `pending` -> `заказ получен`
- `processing` -> `заказ обрабатывается`
- `packaging` -> `заказ собирается`
- `packed` -> `заказ собран`
- `delivering` -> `заказ в пути`
- `client_notified` -> `заказ готов, клиент уведомлен`
- `canceled` -> `заказ отменен`
- `completed` -> `заказ выполнен`
- `draft` -> `черновик`
- `NEW/new` -> `только создан, ожидание обработки`

## Status Hints
- `pending`: заказ получен, ожидает подтверждения оператором.
- `processing`: заказ в обработке, пока не готов.
- `packaging`: заказ собирается, пока не готов.
- `packed`: заказ собран, но еще не готов к выдаче; ориентироваться на `client_notified`.
- `delivering`: заказ в пути.
- `client_notified`: заказ готов к выдаче/получению.
- `canceled`: заказ отменен.
- `completed`: заказ выполнен.
- `draft`: заказ в черновике.
- `new`: заказ только создан, по номеру может не находиться до принятия оператором.

## Critical Interpretation
- `packed` не означает, что заказ уже можно забирать.
- Для готовности к выдаче ориентироваться на `client_notified` и `status_hint`.
- Если заказ только создан и поиск идет по номеру заказа, может потребоваться подождать.

## Tool Description Guidance (for LLM)
- В описании tool зафиксировано:
  - как вводить телефон (международный формат);
  - почему новый заказ по номеру может сразу не находиться;
  - что нужно использовать `status_hint`;
  - что `packed` нельзя трактовать как готовность к выдаче.

## Test Cases
- Unit:
  - валидация пустого `lookup`;
  - проверка регистрации описания tool в MCP;
  - проверка маппинга статусов и `status_hint`.
- Integration-like:
  - проверка GET запроса в stage API;
  - проверка передачи `Authorization`;
  - проверка fallback токена из `.env`.
- E2E:
  - smoke `playwright` (placeholder).

## Implemented Worklog
- Реализован backend tool `track_order_status_ui` (server handler + service + repository).
- Добавлена авторизация через `APTEKA_TRACKING_AUTHORIZATION`.
- Добавлен fallback чтения токена из `.env`, если переменная не экспортирована.
- Добавлен маппинг статусов в пользовательские значения.
- Добавлено поле `status_code` с оригинальным кодом статуса.
- Добавлено поле `status_hint` для корректной интерпретации статуса ИИ.
- Обновлено описание tool для правильных подсказок пользователю.
