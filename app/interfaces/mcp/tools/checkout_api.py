"""Apteka checkout HTTP boundary, adapted from the Kokiko order client."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.domain.cart.entities import CartToken
from app.interfaces.mcp.tools.apteka_urls import build_front_url


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
            {key: str(window[key]) for key in ("deliveryDate", "from", "to")}
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
