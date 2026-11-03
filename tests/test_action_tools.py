"""Distinct MCP actions must keep cart isolation and confirmed-order safeguards."""

from decimal import Decimal

import pytest

from app.domain.cart.entities import CartItem, CartSnapshot, CartToken
from app.interfaces.mcp import server, tool_registry
from app.interfaces.mcp.tools import checkout_tools
from app.interfaces.mcp.tools.cart_tools import InMemoryCartTokenStore


class CartRepository:
    def __init__(self):
        self.carts = {}
        self.created = 0
        self.writes = []

    def create_cart(self):
        self.created += 1
        token = CartToken(f"private-{self.created}", "Bearer")
        self.carts[token.access_token] = {}
        return token

    def get_cart(self, token):
        items = [
            CartItem(product_id=key, quantity=quantity, name=key, price=Decimal("40"))
            for key, quantity in self.carts[token.access_token].items()
        ]
        return CartSnapshot(
            items,
            sum(item.quantity for item in items),
            sum((item.price * item.quantity for item in items), Decimal(0)),
        )

    def update_items(self, token, *, items, item_meta_by_product_id=None):
        self.writes.append((token.access_token, list(items)))
        self.carts[token.access_token] = {key: quantity for key, quantity in items if quantity > 0}
        return self.get_cart(token)


class CheckoutClient:
    def __init__(self):
        self.orders = []

    def reference_data(self, language):
        return {
            "regions": [{"id": 2, "name": "Chisinau", "delivery_cost": 30}],
            "cities": [{"id": 24, "region_id": 2, "name": "Ciocana"}],
            "pharmacies": [
                {"id": 1, "region_id": 2, "city_id": 24, "name": "Farmacia", "address": "Street 1"}
            ],
        }

    def delivery_windows(self, method, destination_id, language):
        return [{"deliveryDate": "03.11.2026", "from": "13:00", "to": "15:00"}]

    def send_order(self, token, payload, language):
        self.orders.append((token.access_token, payload))
        return {"id": 123, "number": "AP-123"}


@pytest.fixture
def actions():
    from app.interfaces.mcp.tools import commerce_actions

    return commerce_actions


@pytest.fixture
def cart_backend():
    return {"repository": CartRepository(), "token_store": InMemoryCartTokenStore()}


@pytest.mark.parametrize(
    "name,readonly,destructive,openworld",
    [
        ("check_cart", True, False, True),
        ("add_to_cart", False, False, True),
        ("update_cart_item", False, True, True),
        ("clear_cart", False, True, True),
        ("get_checkout_options", True, False, True),
        ("get_delivery_windows", True, False, True),
        ("review_order", False, False, True),
        ("submit_order", False, True, True),
        ("open_checkout", True, False, False),
        ("set_widget_theme", False, False, False),
        ("set_widget_language", False, False, False),
    ],
)
def test_distinct_actions_advertise_their_own_side_effects(name, readonly, destructive, openworld):
    descriptor = tool_registry.serialize_tool_definition(tool_registry.create_tool_registry()[name])
    assert descriptor["annotations"] == {
        "readOnlyHint": readonly,
        "destructiveHint": destructive,
        "openWorldHint": openworld,
    }
    assert server._get_tool_cache_ttl_seconds(name) is None
    assert "action" not in descriptor["inputSchema"]["properties"]


def test_legacy_tools_and_internal_session_sync_are_app_only():
    registry = tool_registry.create_tool_registry()
    for name in ("my_cart", "add_to_my_cart", "checkout_order", "sync_cart"):
        descriptor = tool_registry.serialize_tool_definition(registry[name])
        assert descriptor["_meta"]["ui"]["visibility"] == ["app"]


@pytest.mark.parametrize("custom_registry", [False, True])
def test_scan_advertises_only_current_actions(custom_registry):
    expected = {
        "search_products",
        "support_knowledge_search",
        "check_cart",
        "add_to_cart",
        "update_cart_item",
        "clear_cart",
        "search_and_add_to_cart",
        "open_checkout",
        "get_checkout_options",
        "get_delivery_windows",
        "review_order",
        "submit_order",
        "set_widget_theme",
        "set_widget_language",
    }
    server._reset_server_caches_for_tests()
    try:
        options = {"registry": tool_registry.create_tool_registry()} if custom_registry else {}
        response = server.handle_rpc_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            **options,
        )
        tools = response["result"]["tools"]
        assert {tool["name"] for tool in tools} == expected
        assert all(tool["_meta"]["ui"]["visibility"] == ["model", "app"] for tool in tools)
    finally:
        server._reset_server_caches_for_tests()


@pytest.mark.parametrize(
    "arguments",
    [
        {"cart_session_id": "a"},
        {"cart_session_id": "a", "confirmation_id": "review", "terms_accepted": False},
        {
            "cart_session_id": "a",
            "confirmation_id": "review",
            "terms_accepted": True,
            "action": "options",
        },
    ],
)
def test_submit_schema_rejects_missing_confirmation_and_other_actions(arguments):
    result = server.handle_rpc_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "submit_order", "arguments": arguments},
        },
        registry=tool_registry.create_tool_registry(),
    )
    assert result["error"]["code"] == -32602


def test_reading_a_missing_or_expired_cart_never_creates_one(actions, cart_backend):
    for arguments in ({}, {"cart_session_id": "expired"}):
        result = actions.check_cart(arguments, **cart_backend)
        assert result["items"] == []
    assert cart_backend["repository"].created == 0
    assert cart_backend["repository"].writes == []


def test_cart_actions_keep_sessions_isolated_and_use_absolute_updates(actions, cart_backend):
    first = actions.add_to_cart({"product_id": "101", "quantity": 2}, **cart_backend)
    second = actions.add_to_cart({"product_id": "202"}, **cart_backend)
    session = {"cart_session_id": first["cart_session_id"]}
    changed = actions.update_cart_item(
        {**session, "product_id": "101", "quantity": 5}, **cart_backend
    )
    assert changed["items"][0]["quantity"] == 5
    assert actions.clear_cart(session, **cart_backend)["items"] == []
    other = actions.check_cart({"cart_session_id": second["cart_session_id"]}, **cart_backend)
    assert [(item["product_id"], item["quantity"]) for item in other["items"]] == [("202", 1)]
    assert "private-" not in str(first)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_add_only_action_cannot_delete_or_accept_invalid_quantities(
    actions, cart_backend, quantity
):
    with pytest.raises(ValueError):
        actions.add_to_cart({"product_id": "101", "quantity": quantity}, **cart_backend)
    assert cart_backend["repository"].created == 0


def test_updates_cannot_insert_an_unknown_item(actions, cart_backend):
    cart = actions.add_to_cart({"product_id": "101"}, **cart_backend)
    writes = len(cart_backend["repository"].writes)
    with pytest.raises(ValueError, match="cart"):
        actions.update_cart_item(
            {"cart_session_id": cart["cart_session_id"], "product_id": "other", "quantity": 3},
            **cart_backend,
        )
    assert len(cart_backend["repository"].writes) == writes


def test_checkout_preparation_never_submits_and_confirmation_stays_idempotent(
    actions, cart_backend
):
    cart = actions.add_to_cart({"product_id": "101", "quantity": 2}, **cart_backend)
    session = {"cart_session_id": cart["cart_session_id"]}
    client = CheckoutClient()
    deps = {**cart_backend, "client": client}
    before = len(checkout_tools._REVIEWS)
    assert actions.get_checkout_options(session, **deps)["status"] == "delivery_method_selection"
    assert (
        actions.get_delivery_windows(
            {**session, "delivery_method": "pickup", "pharmacy_id": 1}, **deps
        )["status"]
        == "delivery_windows"
    )
    assert len(checkout_tools._REVIEWS) == before
    review = actions.review_order(
        {
            **session,
            "delivery_method": "pickup",
            "pharmacy_id": 1,
            "contact": {"first_name": "Ana", "phone": "+37379802000"},
            "payment_method": "cash_on_receipt",
        },
        **deps,
    )
    assert client.orders == []
    submission = {**session, "confirmation_id": review["confirmation_id"], "terms_accepted": True}
    result = actions.submit_order(submission, **deps)
    assert actions.submit_order(submission, **deps) == result
    assert len(client.orders) == 1
    assert client.orders[0][1]["payment"]["type"] == "cash"


def test_checkout_action_cannot_be_overridden(actions):
    with pytest.raises(ValueError, match="action"):
        actions.get_checkout_options({"action": "submit"})


def test_checkout_without_a_cart_points_to_a_current_tool(actions):
    with pytest.raises(ValueError, match="add_to_cart"):
        actions.get_checkout_options({"cart_session_id": ""})


def test_search_and_add_requires_selection_when_results_are_ambiguous(actions, cart_backend):
    products = [{"id": "101", "price": 40}, {"id": "202", "price": 50}]

    def search(query, **kwargs):
        return {"products": products, "query": query}

    result = actions.search_and_add_to_cart({"query": "cream"}, searcher=search, **cart_backend)
    assert result["status"] == "selection_required"
    assert cart_backend["repository"].created == 0
    chosen = actions.search_and_add_to_cart(
        {"query": "cream", "product_id": "202"}, searcher=search, **cart_backend
    )
    assert chosen["items"][0]["product_id"] == "202"


def test_search_and_add_does_not_treat_upstream_failure_as_no_results(actions, cart_backend):
    result = actions.search_and_add_to_cart(
        {"query": "cream"},
        searcher=lambda *args, **kwargs: {"products": [], "upstream_error": {"retryable": True}},
        **cart_backend,
    )
    assert result["status"] == "search_unavailable"
    assert cart_backend["repository"].created == 0


def test_preferences_and_open_checkout_do_not_touch_a_backend(actions, cart_backend):
    assert actions.set_widget_theme({"theme": "dark"})["theme_mode"] == "manual"
    assert actions.set_widget_theme({"theme": "auto"})["auto_disabled"] is False
    assert actions.set_widget_language({"language": "ro"})["language"] == "ro"
    assert actions.open_checkout({"cart_session_id": "a"})["checkout_step"] == "delivery"
    assert cart_backend["repository"].created == 0


def test_readonly_checkout_cannot_recreate_a_token_that_expires_during_the_read(
    actions, cart_backend
):
    cart = actions.add_to_cart({"product_id": "101"}, **cart_backend)
    original_store = cart_backend["token_store"]
    token = original_store.get_token(cart["cart_session_id"])

    class ExpiringStore:
        reads = 0

        def get_token(self, session_id):
            self.reads += 1
            return token if self.reads == 1 else None

        def set_token(self, *args):
            pytest.fail("A read-only checkout tool must not renew an expired cart")

    before = cart_backend["repository"].created
    result = actions.get_checkout_options(
        {"cart_session_id": cart["cart_session_id"]},
        repository=cart_backend["repository"],
        token_store=ExpiringStore(),
        client=CheckoutClient(),
    )
    assert result["status"] == "cart_empty"
    assert cart_backend["repository"].created == before


def test_search_descriptor_does_not_claim_that_production_is_a_stage_api():
    assert "Stage API" not in tool_registry.create_tool_registry()["search_products"].description
