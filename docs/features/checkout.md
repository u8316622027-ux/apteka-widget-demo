# Feature: checkout

## Goal
Провести пользователя через оформление заказа по строгой цепочке:
1. Проверка корзины.
2. Выбор способа доставки.
3. Ветвление на самовывоз или курьер.
4. Для самовывоза: подтверждение + оплата + отправка заказа.

## Flow Rules
1. `checkout_order` всегда начинается с проверки корзины.
2. Если корзина пустая: вернуть `cart_empty` и попросить добавить товары.
3. Если корзина не пустая: вернуть `delivery_method_selection`.
4. Переход на следующий шаг только после обязательных данных текущего шага.
5. Если пользователь передал сразу несколько обязательных полей, tool пропускает его до первого реально недостающего шага.
6. Автовыбор:
   - если после выбора региона доступен только один населенный пункт/сектор, он выбирается автоматически;
   - если после выбора населенного пункта доступна только одна аптека, она выбирается автоматически;
   - если одновременно один населенный пункт и одна аптека, переход сразу на шаг контактов.

## Pickup Branch
1. `pickup_contact_and_region`: показать регионы, где есть аптеки.
2. `pickup_city_selection`: после выбора региона показать населенные пункты/секторы с аптеками.
3. `pickup_pharmacy_selection`: после выбора населенного пункта/сектора показать доступные аптеки.
4. `pickup_contact`: после выбора аптеки загрузить окно выдачи заказа.
5. `pickup_confirmation_and_payment`: после успешной валидации контактных данных вернуть review + оплату + confirmations.
6. `order_submitted`: заказ успешно отправлен в API подтверждения.

## Courier Branch
1. `courier_contact_and_region`: вернуть список регионов и требования к контактам.
2. `courier_city_selection`: после региона вернуть населенные пункты этого региона.
3. `courier_contact_and_address`: запросить контакты и адрес.
4. `courier_ready_for_submission`: вернуть нормализованные контакт/адрес и review payload.

## Pickup Time Window API
- Endpoint: `GET /api/v1/front/delivery/calculate/pick-up/{pharmacy_id}`
- Когда вызывается: после выбора аптеки (вручную или автоподбором).
- Что возвращается в tool: `pickup_window`, например:
  - `deliveryDate`
  - `from`
  - `to`
  - `orderEnd`
  - `pharmacyClose`

## Inputs
- `cart_session_id` (необязательный)
- `delivery_method` (`pickup` или `courier_delivery`)
- `pickup_region_id` / `pickup_region_name` (необязательные)
- `pickup_city_id` / `pickup_city_name` (необязательные)
- `pickup_pharmacy_id` / `pickup_pharmacy_name` (необязательные)
- `pickup_contact`:
  - `first_name` обязательно, минимум 3 символа
  - `last_name` необязательно, но если передано, минимум 3 символа
  - `phone` обязательно
  - `email` необязательно
- `courier_contact` (те же правила, что у `pickup_contact`)
- `courier_address`:
  - required: `street`, `house_number`
  - optional: `apartment`, `entrance`, `floor`, `intercom_code`
- `payment_method` (для pickup submit)
- `terms_accepted` (для pickup submit, должно быть `true`)
- `dont_call_me` (optional, default false в confirm payload)
- `comment` необязательный текст

## Status Values
- `cart_empty`
- `delivery_method_selection`
- `pickup_contact_and_region`
- `pickup_city_selection`
- `pickup_pharmacy_selection`
- `pickup_contact`
- `pickup_confirmation_and_payment`
- `order_submitted`
- `order_submission_failed`
- `courier_contact_and_region`
- `courier_city_selection`
- `courier_contact_and_address`
- `courier_ready_for_submission`
- `validation_error`

## Data Filtering Rules
- `available_regions`: только регионы, где есть хотя бы одна аптека.
- `available_cities`: населенные пункты/секторы выбранного региона, где есть хотя бы одна аптека.
- `available_pharmacies`: только аптеки выбранной пары `region + city/sector`.
- В UI для выбора региона и населенного пункта отдаются только названия (без id).
- Для зон, которых нет в `cities-without-regions`, используется fallback из `pharmacies.new-list` по `sector`.

## Validation
- Имя/фамилия: правила минимальной длины.
- Телефон: whitelist по `app/data/allowed_phone_codes.json`.
- Email: `email_validator`, если библиотека доступна, иначе fallback на regex.
- Для submit самовывоза обязательны `payment_method` и `terms_accepted = true`.

## Confirmation and Payment (Pickup)
- После валидного `pickup_contact` tool возвращает `pickup_confirmation_and_payment` с cart/customer/delivery review.
- Payment options:
  - `card_on_receipt`
  - `cash_on_receipt`
  - `bank_transfer`
- Submit endpoint: `POST /api/v1/front/order/confirm-order-by-using-mobile`.
- При неуспешной отправке возвращается `order_submission_failed`.

## Phone Whitelist
- Allowed phone metadata хранится в `app/data/allowed_phone_codes.json`.
- Проверка принимает только номера, соответствующие `dial_code + min_length/max_length`.

## Tech Debt / Next Improvements
- Добавить полноценный submit для courier-ветки.
- Добавить явный id-контракт для region/city/pharmacy в публичной документации API.
