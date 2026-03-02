# Feature: checkout

## Goal
Guide user through checkout in a strict sequence:
1. Delivery method.
2. Personal data + address branch (pickup/courier).
3. Confirmation + payment (not implemented yet).

## Flow Rules
1. `checkout_order` always starts with cart check.
2. If cart is empty: return `cart_empty` and ask to add products.
3. If cart has items: return `delivery_method_selection`.
4. User cannot jump directly to later stages without required previous data.
5. Exception: if user provides multiple required fields in one message, tool skips directly to the first missing step.

## Pickup Branch
1. `pickup_contact_and_region`: show regions with pharmacies.
2. `pickup_city_selection`: after region selected, show cities with pharmacies.
3. `pickup_pharmacy_selection`: after city selected, show pharmacies.
4. `pickup_contact`: after pharmacy selected, load pickup time window.
5. `pickup_ready_for_submission`: after valid contact details.

## Pickup Time Window API
- Endpoint: `GET /api/v1/front/delivery/calculate/pick-up/{pharmacy_id}`
- Trigger: right after pharmacy selection.
- Returned payload is exposed as `pickup_window`, for example:
  - `deliveryDate`
  - `from`
  - `to`
  - `orderEnd`
  - `pharmacyClose`

## Inputs
- `cart_session_id` (optional)
- `delivery_method` (`pickup` or `courier_delivery`)
- `pickup_region_id` (optional)
- `pickup_city_id` (optional)
- `pickup_pharmacy_id` (optional)
- `pickup_contact`:
  - `first_name` required, min 3
  - `last_name` optional, if provided min 3
  - `phone` required
  - `email` optional
- `comment` optional text

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
- `available_regions`: only regions where at least one pharmacy exists.
- `available_cities`: only cities from selected region where at least one pharmacy exists.
- `available_pharmacies`: only pharmacies for selected `region + city`.
- Region/city options are returned as display objects only: `{"id", "name"}`.

## Validation
- Name/last name min-length rules.
- Phone validation: `phonenumbers` when available, regex fallback.
- Email validation: `email_validator` when available, regex fallback.

## Current Limitations
- Courier branch is not implemented yet.
- Country allowlist for phone validation will be added later.
