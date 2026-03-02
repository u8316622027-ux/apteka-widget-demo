# Feature: checkout

## Goal
Провести пользователя через checkout по шагам, начиная с выбора способа доставки, и собрать данные для `pickup` одним payload.

## User Flow
1. `checkout_order` без `delivery_method`:
   - проверяет корзину;
   - при пустой корзине возвращает `cart_empty`;
   - при непустой корзине возвращает `delivery_method_selection`.
2. `checkout_order` с `delivery_method=pickup`:
   - возвращает шаг контактов + доступных регионов (`pickup_contact_and_region`), если еще не выбран регион;
   - после выбора региона возвращает доступные населенные пункты (`pickup_city_selection`);
   - после выбора населенного пункта возвращает список аптек (`pickup_pharmacy_selection`);
   - после передачи контактов и комментария валидирует и возвращает финальный payload для одной отправки (`pickup_ready_for_submission`).

## Inputs/Outputs
- Inputs:
  - `cart_session_id` (optional)
  - `delivery_method`: `pickup | courier_delivery` (optional)
  - `pickup_region_id` (optional)
  - `pickup_city_id` (optional)
  - `pickup_contact`:
    - `first_name` (required, min 3)
    - `last_name` (optional, if provided min 3)
    - `phone` (required)
    - `email` (optional)
  - `comment` (optional, text only)
- Outputs:
  - `status`:
    - `cart_empty`
    - `delivery_method_selection`
    - `pickup_contact_and_region`
    - `pickup_city_selection`
    - `pickup_pharmacy_selection`
    - `pickup_ready_for_submission`
    - `validation_error`

## Reference Data Logic
- При первом checkout-запросе загружаются и кешируются:
  - `GET /regions`
  - `GET /cities-without-regions`
  - `GET /pharmacies/new-list`
- `available_regions`:
  - только те регионы, у которых есть хотя бы одна аптека в `pharmacies.region.id`.
- `available_cities`:
  - только населенные пункты из выбранного региона;
  - только те, для которых найдена аптека в выбранном регионе.
- `available_pharmacies`:
  - только аптеки выбранной пары `region + city`.

## Validation Rules
- Имя: обязательно, минимум 3 символа.
- Фамилия: необязательно, но если передана, минимум 3 символа.
- Телефон:
  - сначала пробуется `phonenumbers` (если библиотека доступна);
  - fallback: базовая E.164-проверка regex.
- Email:
  - сначала пробуется `email_validator` (если библиотека доступна);
  - fallback: базовая проверка regex.

## Current Limitations
- `courier_delivery` пока не реализован (`courier_delivery_not_implemented`).
- Для строгих правил по телефону по списку стран нужен отдельный allowlist стран (будет добавлен после передачи списка).

## Test Cases
- Unit:
  - проверка `cart_empty`;
  - префетч и кеш reference-data;
  - фильтрация регионов по наличию аптек;
  - фильтрация населенных пунктов по региону и наличию аптек;
  - выдача аптек для выбранного региона/населенного пункта;
  - валидация контактов;
  - успешная сборка `pickup_ready_for_submission`.
- Server wiring:
  - делегирование `checkout_order` из MCP server с новыми аргументами.
