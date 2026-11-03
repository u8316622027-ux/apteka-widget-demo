"""Apteka checkout HTTP boundary, adapted from the Kokiko order client."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.domain.cart.entities import CartToken
from app.interfaces.mcp.tools.apteka_urls import build_front_url


class OrderValidationError(ValueError):
    """An explicit HTTP 422 rejection; the order was not accepted."""

    status_code = 422
    _FIELD_LABELS = {
        "payment.type": ("способ оплаты", "metoda de plată"),
        "delivery.phone": ("телефон", "telefonul"),
        "delivery.firstName": ("имя", "prenumele"),
        "delivery.lastName": ("фамилия", "numele"),
        "delivery.email": ("email", "emailul"),
        "delivery.pharmacy_id": ("аптека", "farmacia"),
        "delivery.address.street": ("улица", "strada"),
        "delivery.address.building": ("номер дома", "numărul casei"),
        "delivery.address.region_id": ("регион", "regiunea"),
        "delivery.address.sector_id": ("населённый пункт", "localitatea"),
        "delivery.deliveryWindow": ("время доставки", "intervalul de livrare"),
        "dontCallMe": ("настройка звонка", "preferința pentru apel"),
        "items": ("корзина", "coșul"),
    }

    def __init__(self, fields=(), *, language="ru"):
        # Only known field names leave the HTTP boundary, never raw upstream bodies.
        self.fields = tuple(field for field in fields if field in self._FIELD_LABELS)
        romanian = str(language).startswith("ro")
        labels = [self._FIELD_LABELS[field][int(romanian)] for field in self.fields]
        details = ", ".join(labels) or ("datele comenzii" if romanian else "данные заказа")
        prefix = (
            "Comanda nu a fost acceptată (HTTP 422). Verificați"
            if romanian
            else ("Заказ не принят (HTTP 422). Проверьте")
        )
        super().__init__(f"{prefix}: {details}.")


class AptekaCheckoutClient:
    def __init__(self, *, opener=urlopen, timeout: float = 15):
        self._opener = opener
        self._timeout = timeout

    def _request(self, path, language, *, token=None, payload=None):
        headers = {"Accept": "application/json", "Accept-Language": language, "platform": "web"}
        if token:
            headers["Authorization"] = f"{token.token_type} {token.access_token}"
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            build_front_url(path),
            data=data,
            headers=headers,
            method="POST" if data is not None else "GET",
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 422 and path == "/order/confirm-order-by-using-mobile":
                try:
                    rejection = json.loads(exc.read(65536).decode("utf-8", errors="replace"))
                except (ValueError, OSError):
                    rejection = {}
                fields = rejection.get("errors") if isinstance(rejection, dict) else {}
                raise OrderValidationError(
                    fields.keys() if isinstance(fields, dict) else (), language=language
                ) from exc
            # Avoid reflecting upstream bodies containing personal data or credentials.
            raise ValueError(f"Apteka API request failed (HTTP {exc.code})") from exc

    def reference_data(self, language: str) -> dict[str, list[dict[str, Any]]]:
        regions = self._request("/regions", language)
        cities = self._request("/cities-without-regions", language)
        pharmacies = self._request("/pharmacies/list", language)

        def title(item, key="name"):
            translations = item.get("translations") or {}
            return str((translations.get(language) or translations.get("ru") or {}).get(key) or "")

        normalized_cities = {
            int(item["id"]): {
                "id": int(item["id"]),
                "region_id": int(item["region_id"]),
                "name": title(item),
            }
            for item in cities
            if item.get("id") and item.get("region_id")
        }
        normalized_pharmacies = []
        for item in pharmacies:
            region = item.get("region") or {}
            sector = item.get("sector") or {}
            if not region.get("id") or not sector.get("id"):
                continue
            city_id = int(sector["id"])
            normalized_cities.setdefault(
                city_id,
                {
                    "id": city_id,
                    "region_id": int(region["id"]),
                    "name": title(sector),
                },
            )
            normalized_pharmacies.append(
                {
                    "id": int(item["id"]),
                    "region_id": int(region["id"]),
                    "city_id": city_id,
                    "name": title(item),
                    "address": title(item, "address"),
                    "schedule": item.get("schedule") or {},
                }
            )
        return {
            "regions": [
                {
                    "id": int(item["id"]),
                    "name": title(item),
                    "delivery_cost": item.get("deliveryCost") or 0,
                    "free_shipping_cost": item.get("freeShippingCost"),
                }
                for item in regions
            ],
            "cities": list(normalized_cities.values()),
            "pharmacies": normalized_pharmacies,
        }

    def delivery_windows(self, method: str, destination_id: int, language: str):
        route = "pick-up" if method == "pickup" else "target"
        payload = self._request(f"/delivery/calculate/{route}/{destination_id}", language)
        groups = payload.get("availableWindows") or {}
        windows = [window for group in groups.values() for window in group] if groups else [payload]
        return [
            {
                **{key: str(window[key]) for key in ("deliveryDate", "from", "to")},
                **{
                    key: str(payload[key])
                    for key in ("orderEnd", "pharmacyClose")
                    if payload.get(key)
                },
            }
            for window in windows
            if all(window.get(k) for k in ("deliveryDate", "from", "to"))
        ]

    def send_order(self, token: CartToken, payload: dict, language: str):
        result = self._request(
            "/order/confirm-order-by-using-mobile",
            language,
            token=token,
            payload=payload,
        )
        if not isinstance(result, dict) or not result.get("id"):
            raise ValueError("Apteka API did not return an order id; verify the order status")
        return {"id": str(result["id"]), "number": result.get("number")}
