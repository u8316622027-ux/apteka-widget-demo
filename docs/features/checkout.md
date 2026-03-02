# Feature: checkout

## Goal
Провести пользователя через оформление заказа по строгой цепочке:
1. Выбор способа доставки.
2. Ветвление на заполнение личных данных и адреса (самовывоз/курьер).
3. Подтверждение и способ оплаты (пока не реализовано).

## Flow Rules
1. `checkout_order` всегда начинается с проверки корзины.
2. Если корзина пустая: вернуть `cart_empty` и попросить добавить товары.
3. Если корзина не пустая: вернуть `delivery_method_selection`.
4. Пользователь не может перейти на поздний этап без заполнения обязательных данных предыдущих шагов.
5. Исключение: если пользователь в одном сообщении передал несколько обязательных полей, tool пропускает его до первого недостающего шага.

## Pickup Branch
1. `pickup_contact_and_region`: показать регионы, где есть аптеки.
2. `pickup_city_selection`: после выбора региона показать населенные пункты, где есть аптеки.
3. `pickup_pharmacy_selection`: после выбора населенного пункта показать доступные аптеки.
4. `pickup_contact`: после выбора аптеки загрузить окно выдачи заказа.
5. `pickup_ready_for_submission`: после успешной валидации контактных данных.

## Pickup Time Window API
- Endpoint: `GET /api/v1/front/delivery/calculate/pick-up/{pharmacy_id}`
- Когда вызывается: сразу после выбора аптеки.
- Что возвращается в tool: `pickup_window`, например:
  - `deliveryDate`
  - `from`
  - `to`
  - `orderEnd`
  - `pharmacyClose`

## Inputs
- `cart_session_id` (необязательный)
- `delivery_method` (`pickup` или `courier_delivery`)
- `pickup_region_id` (необязательный)
- `pickup_city_id` (необязательный)
- `pickup_pharmacy_id` (необязательный)
- `pickup_contact`:
  - `first_name` обязательно, минимум 3 символа
  - `last_name` необязательно, но если передано, минимум 3 символа
  - `phone` обязательно
  - `email` необязательно
- `comment` необязательный текст

## Status Values
- `cart_empty`
- `delivery_method_selection`
- `pickup_contact_and_region`
- `pickup_city_selection`
- `pickup_pharmacy_selection`
- `pickup_contact`
- `pickup_ready_for_submission`
- `validation_error`
- `courier_delivery_not_implemented`

## Data Filtering Rules
- `available_regions`: только регионы, где есть хотя бы одна аптека.
- `available_cities`: только населенные пункты выбранного региона, где есть хотя бы одна аптека.
- `available_pharmacies`: только аптеки выбранной пары `region + city`.
- Варианты региона/населенного пункта возвращаются только в display-формате: `{"id", "name"}`.

## Validation
- Имя/фамилия: правила минимальной длины.
- Телефон: `phonenumbers`, если библиотека доступна, иначе fallback на regex.
- Email: `email_validator`, если библиотека доступна, иначе fallback на regex.

## Current Limitations
- Ветка `courier_delivery` пока не реализована.
- Список разрешенных стран для строгой проверки телефона будет добавлен отдельно.
