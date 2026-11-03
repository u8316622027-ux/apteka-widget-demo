"""Schemas and metadata for separate cart, checkout and preference actions."""

from app.interfaces.mcp.tool_definition import ToolDefinition
from app.interfaces.mcp.tools import commerce_actions as actions


def create_action_registry(ui, template, checkout_properties):
    session = {
        "type": "string",
        "description": "Reuse this user's cart_session_id; never guess it.",
    }
    language = {"type": "string", "enum": ["ru", "ro"]}
    product = {
        "type": "string",
        "description": "Exact product id from search results or this cart.",
    }
    quantity = {"type": "integer", "minimum": 0}
    cart = {"cart_session_id": session}
    checkout = {**cart, "language": language}
    registry = {}

    def register(
        name,
        title,
        description,
        properties,
        required=(),
        *,
        readonly=False,
        destructive=False,
        openworld=True,
        visibility="public",
    ):
        registry[name] = ToolDefinition(
            name=name,
            title=title,
            description=description,
            input_schema={
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
            handler=getattr(actions, name),
            output_template=template,
            ui=ui,
            annotations={
                "readOnlyHint": readonly,
                "destructiveHint": destructive,
                "openWorldHint": openworld,
            },
            visibility=visibility,
            tool_invocation={"invoking": "Loading…", "invoked": "Done."},
        )

    register(
        "check_cart",
        "Check cart",
        "Show this user's existing cart and API totals without creating or changing it. "
        "Reuse cart_session_id from prior results; without a session the cart is empty.",
        cart,
        readonly=True,
    )
    register(
        "add_to_cart",
        "Add to cart",
        "Add a selected product to this user's cart. quantity is a positive increment. "
        "Reuse cart_session_id; omit it only for a new cart. "
        "Does not remove items or place orders.",
        {**cart, "product_id": product, "quantity": {**quantity, "minimum": 1}},
        ("product_id",),
    )
    register(
        "update_cart_item",
        "Update cart item",
        "Set the absolute quantity of one item already in this user's cart. "
        "Zero removes the item; updates overwrite its previous quantity without automatic undo.",
        {**cart, "product_id": product, "quantity": quantity},
        ("cart_session_id", "product_id", "quantity"),
        destructive=True,
    )
    register(
        "clear_cart",
        "Clear cart",
        "Remove all items from this user's cart. This overwrites the cart without automatic undo. "
        "Only use when the user asks to clear it; never affects another cart.",
        cart,
        ("cart_session_id",),
        destructive=True,
    )
    register(
        "sync_cart",
        "Initialize or restore cart session",
        "Internal widget session initialization and refresh. Creates a cart only if needed, "
        "otherwise reads it. Never replaces backend items with browser-supplied prices.",
        cart,
        visibility="app",
    )
    register(
        "search_and_add_to_cart",
        "Search and add to cart",
        "Use for a request to find and add a product. Adds an explicitly selected result or "
        "a unique priced match. Ambiguous results require selection and do not modify the cart. "
        "Reuse cart_session_id. Does not submit an order.",
        {
            **cart,
            "query": {"type": "string"},
            "language": language,
            "quantity": {**quantity, "minimum": 1},
            "product_id": product,
            "product_index": {"type": "integer", "minimum": 1},
        },
        ("query",),
    )
    register(
        "open_checkout",
        "Open checkout",
        "Open the checkout form for this user's cart. Navigation only; does not submit an order. "
        "Use review_order before submit_order after the user supplies the required details.",
        checkout,
        readonly=True,
        openworld=False,
    )
    register(
        "get_checkout_options",
        "Get checkout options",
        "Read available delivery regions, cities and pickup pharmacies for this cart. "
        "Does not create, change or submit an order and does not require contact details.",
        checkout,
        ("cart_session_id",),
        readonly=True,
    )
    register(
        "get_delivery_windows",
        "Get delivery windows",
        "Read available delivery times for the selected pharmacy (pickup) or region (courier). "
        "Does not create, change or submit an order and does not require contact details.",
        {
            key: checkout_properties[key]
            for key in (
                "cart_session_id",
                "language",
                "delivery_method",
                "pharmacy_id",
                "region_id",
            )
        },
        ("cart_session_id", "delivery_method"),
        readonly=True,
    )
    register(
        "review_order",
        "Review order",
        "Validate this user's cart, contact, destination, delivery time and payment on receipt. "
        "Returns a temporary confirmation_id and exact order summary for explicit user approval. "
        "Stores only a review; it does not send or create an order.",
        {
            key: value
            for key, value in checkout_properties.items()
            if key not in {"action", "confirmation_id", "terms_accepted"}
        },
        ("cart_session_id", "contact", "delivery_method", "payment_method"),
    )
    register(
        "submit_order",
        "Submit confirmed order",
        "Create a real Apteka order by sending a previously reviewed cart's contact and delivery "
        "details to Apteka. Only call after the user explicitly approves that exact review and "
        "accepts the terms. Requires its confirmation_id and the same cart_session_id. "
        "This tool cannot cancel the order. Payment is cash or card upon receipt; no card "
        "credentials are collected. Never invent contact data or retry an uncertain submission.",
        {
            **cart,
            "confirmation_id": {"type": "string"},
            "terms_accepted": {"type": "boolean", "enum": [True]},
        },
        ("cart_session_id", "confirmation_id", "terms_accepted"),
        destructive=True,
    )
    register(
        "set_widget_theme",
        "Set widget theme",
        "Switch the widget theme to light, dark or auto when the user asks. Changes UI only.",
        {"theme": {"type": "string", "enum": ["light", "dark", "auto"]}},
        ("theme",),
        openworld=False,
    )
    register(
        "set_widget_language",
        "Set widget language",
        "Switch the widget language to Russian (ru) or Romanian (ro) when the user asks.",
        {"language": language},
        ("language",),
        openworld=False,
    )
    return registry
