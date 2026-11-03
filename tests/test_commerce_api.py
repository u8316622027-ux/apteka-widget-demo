"""Wire contracts captured from the current Apteka cart and delivery API."""

import io
import json
from decimal import Decimal

import pytest

from app.domain.cart.entities import CartToken
from app.interfaces.mcp import server
from app.interfaces.mcp.tools.cart.mappers import map_cart_snapshot
from app.interfaces.mcp.tools.cart.repository import AptekaCartRepository
from app.interfaces.mcp.tools.checkout_api import AptekaCheckoutClient


@pytest.mark.parametrize("api_base", ["https://stage.apteka.md", "https://api.apteka.md"])
def test_cart_and_order_use_the_same_selected_environment(monkeypatch, api_base):
    monkeypatch.setenv("APTEKA_BASE_URL", api_base)
    requests = []

    def opener(request, **_):
        requests.append(request)
        if request.full_url.endswith("/cart"):
            if request.get_header("Authorization"):
                return io.BytesIO(b'{"items":[],"amount_mdl":0}')
            return io.BytesIO(b'{"accessToken":"environment-token","tokenType":"Bearer"}')
        return io.BytesIO(b'{"id":123}')

    cart = AptekaCartRepository(urlopen=opener)
    token = cart.create_cart()
    cart.get_cart(token)
    AptekaCheckoutClient(opener=opener).send_order(token, {"delivery": {"type": "pick-up"}}, "ru")

    assert [request.full_url for request in requests] == [
        f"{api_base}/api/v1/front/cart",
        f"{api_base}/api/v1/front/cart",
        f"{api_base}/api/v1/front/order/confirm-order-by-using-mobile",
    ]
    assert requests[-1].get_header("Authorization") == "Bearer environment-token"


def test_map_production_cart_details_and_server_total():
    cart = map_cart_snapshot(
        {
            "amount_mdl": 150.94,
            "items": [
                {
                    "product_id": 26156,
                    "quantity": 2,
                    "details": {
                        "translations": {"ru": {"name": "Парацетамол"}},
                        "price": 75.87,
                        "discountPrice": 75.47,
                        "manufacturer": "Medinfar",
                        "images": [{"preview": "https://api.apteka.md/p.webp"}],
                    },
                }
            ],
        }
    )
    assert cart.total == Decimal("150.94")
    assert cart.count == 2
    assert cart.items[0].name == "Парацетамол"
    assert cart.items[0].discount_price == Decimal("75.47")
    assert cart.items[0].image_url == "https://api.apteka.md/p.webp"


def test_zero_discount_uses_regular_price():
    cart = map_cart_snapshot(
        {"items": [{"product_id": 1, "quantity": 2, "price": 40, "discount_price": 0}]}
    )
    assert cart.items[0].discount_price is None
    assert cart.total == Decimal("80.00")


def test_cart_photos_use_selected_media_host(monkeypatch):
    monkeypatch.setenv("APTEKA_MEDIA_BASE_URL", "https://api.apteka.md")
    cart = map_cart_snapshot(
        {
            "items": [
                {
                    "product_id": 1,
                    "quantity": 1,
                    "details": {
                        "translations": {"ru": {"name": "Product"}},
                        "price": 40,
                        "images": [{"preview": "https://stage.apteka.md/media/1/preview.webp"}],
                    },
                }
            ]
        }
    )
    assert cart.items[0].image_url == "https://api.apteka.md/media/1/preview.webp"


def test_checkout_submission_sends_bearer_and_real_payload(monkeypatch):
    monkeypatch.setenv("APTEKA_BASE_URL", "https://api.example")
    requests = []

    def opener(request, **_):
        requests.append(request)
        return io.BytesIO(b'{"id":123,"number":"AP-123"}')

    client = AptekaCheckoutClient(opener=opener)
    order = {"delivery": {"type": "pick-up", "pharmacy_id": 1}}
    result = client.send_order(CartToken("secret", "Bearer"), order, "ro")
    assert result == {"id": "123", "number": "AP-123"}
    assert (
        requests[0].full_url
        == "https://api.example/api/v1/front/order/confirm-order-by-using-mobile"
    )
    assert requests[0].get_header("Authorization") == "Bearer secret"
    assert requests[0].get_header("Accept-language") == "ro"
    assert json.loads(requests[0].data) == order


def test_http_success_without_order_id_is_not_a_success(monkeypatch):
    monkeypatch.setenv("APTEKA_BASE_URL", "https://api.example")
    client = AptekaCheckoutClient(opener=lambda *_, **__: io.BytesIO(b'{"errors":[]}'))
    with pytest.raises(ValueError, match="order id"):
        client.send_order(CartToken("secret", "Bearer"), {}, "ru")


@pytest.mark.parametrize(
    "arguments,schema",
    [
        ({"price": 1}, {"type": "object", "properties": {}, "additionalProperties": False}),
        ([], {"type": "array", "minItems": 1}),
    ],
)
def test_tool_schema_rejects_unknown_fields_and_empty_updates(arguments, schema):
    assert server._validate_value(arguments, schema, path="arguments") is not None
