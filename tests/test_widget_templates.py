"""Tests for static widget template mocks."""

from __future__ import annotations

from pathlib import Path
import unittest


class WidgetTemplateTests(unittest.TestCase):
    def test_all_tool_templates_exist(self) -> None:
        widget_dir = Path("app/widgets")
        expected_templates = {
            "products.html",
            "add-to-my-cart.html",
            "my-cart.html",
            "checkout.html",
            "faq.html",
            "tracking.html",
            "theme.html",
        }
        existing_templates = {path.name for path in widget_dir.glob("*.html")}
        for template_name in expected_templates:
            self.assertIn(template_name, existing_templates)

    def test_templates_use_shared_mock_layout_shell(self) -> None:
        widget_dir = Path("app/widgets")
        template_names = (
            "products.html",
            "add-to-my-cart.html",
            "my-cart.html",
            "checkout.html",
            "faq.html",
            "tracking.html",
            "theme.html",
        )
        for template_name in template_names:
            template_text = (widget_dir / template_name).read_text(encoding="utf-8")
            if template_name == "products.html":
                self.assertNotIn("tailwind.css", template_text)
            else:
                self.assertIn("tailwind.css", template_text)
            self.assertIn("data-widget-shell=", template_text)
            self.assertIn("x-data=", template_text)
            self.assertIn("alpinejs", template_text)

    def test_products_template_matches_search_mock_layout(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('class="search-toolbar"', template_text)
        self.assertIn('class="product-carousel"', template_text)
        self.assertIn('class="product-card"', template_text)
        self.assertIn('class="carousel-arrow left"', template_text)
        self.assertIn('class="carousel-arrow right"', template_text)

    def test_products_template_does_not_have_inline_style_fallback(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertNotIn('data-inline-widget-style="products"', template_text)

    def test_products_template_has_desktop_carousel_and_tablet_layout(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", compact)
        self.assertIn("width:calc(100%+190px)", compact)
        self.assertIn("@media(max-width:930px)", compact)
        self.assertIn("@media(max-width:620px)", compact)

    def test_products_template_has_bottom_controls(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('class="carousel-bottom"', template_text)
        self.assertIn('class="center-indicator"', template_text)
        self.assertGreaterEqual(template_text.count('class="center-indicator"'), 2)
        self.assertIn('class="products-icon products-icon--truck"', template_text)
        self.assertIn('class="products-icon products-icon--headset"', template_text)
        self.assertNotIn('class="section-divider"', template_text)

    def test_products_template_limits_widget_height(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn("align-items:flex-start", compact)
        self.assertNotIn("overflow-y:auto", compact)
        self.assertNotIn("max-height:calc(100vh-32px)", compact)

    def test_products_template_uses_inline_bundle_for_apps_sdk(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertNotIn('href="./styles/widget-products.css"', template_text)
        self.assertNotIn('src="./scripts/widget-shell.js"', template_text)
        self.assertIn("<style>", template_text)
        self.assertIn("<script>", template_text)

    def test_products_template_uses_clickable_official_logo(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('href="https://www.apteka.md/"', template_text)
        self.assertIn('class="search-logo-image"', template_text)
        self.assertIn(
            'src="https://www.apteka.md/_next/static/media/BigLogo.50692667.svg"',
            template_text,
        )

    def test_products_template_removes_top_labels_and_shell_card(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertNotIn("Вызываемый инструмент", template_text)
        self.assertNotIn('class="brand-row"', template_text)
        self.assertNotIn("Найдено товаров:", template_text)

    def test_products_template_uses_transparent_background(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn("background:transparent", compact)
        self.assertNotIn("background:#1a1d23", compact)

    def test_products_template_calls_search_tool(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('window.openai.callTool("search_products"', template_text)
        self.assertNotIn("https://stage.apteka.md/api/v1/front/search", template_text)
        self.assertIn("localStorage", template_text)
        self.assertIn("api_base_url", template_text)
        self.assertNotIn('|| "аспирин"', template_text)
        self.assertNotIn("renderProducts();\n        searchProducts(", template_text)

    def test_products_template_reads_initial_tool_payload_before_manual_search(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("const extractInitialToolPayload", template_text)
        self.assertIn("window.openai", template_text)
        self.assertIn("INITIAL_PAYLOAD_WAIT_MS", template_text)
        self.assertIn("window.addEventListener(\"message\",", template_text)
        self.assertIn("window.setInterval", template_text)

    def test_products_template_has_interactive_carousel_track(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('class="product-track"', template_text)
        self.assertIn('class="carousel-arrow-wrap left"', template_text)
        self.assertIn('class="carousel-arrow-wrap right"', template_text)
        self.assertIn('class="carousel-arrow left"', template_text)
        self.assertIn('class="carousel-arrow right"', template_text)
        self.assertIn("scrollBy", template_text)
        self.assertIn('target.closest(\'[data-action="add-to-cart"]\')', template_text)
        self.assertIn("target instanceof Element ? target.closest", template_text)
        self.assertIn("target?.parentElement?.closest", template_text)
        self.assertIn("event.composedPath", template_text)
        self.assertIn('querySelectorAll(\'[data-action="add-to-cart"]\')', template_text)

    def test_products_template_normalizes_product_image_urls(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("const resolveImageUrl", template_text)
        self.assertIn("new URL(imageUrl, baseUrl)", template_text)
        self.assertIn("const getFallbackImage", template_text)
        self.assertIn('"/assets/images/placeholder-600x600.png"', template_text)
        self.assertNotIn("https://api.apteka.md/assets/images/placeholder-600x600.png", template_text)

    def test_products_template_maps_name_from_ru_ro_fields(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("normalizeText(item.name_ru)", template_text)
        self.assertIn("normalizeText(item.name_ro)", template_text)

    def test_products_template_uses_fixed_card_content_zones(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("display: grid;", template_text)
        self.assertIn("grid-template-rows: 210px", template_text)
        self.assertIn("line-clamp", template_text)
        self.assertIn("product-price-row", template_text)
        self.assertIn("product-manufacturer-row", template_text)

    def test_products_template_uses_non_overlay_arrow_wraps(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn("background:transparent", compact)
        self.assertIn("width:34px", compact)
        self.assertIn("height:86px", compact)
        self.assertIn("border-radius:18px", compact)
        self.assertIn("backdrop-filter:blur(3px)", compact)
        self.assertIn('class="products-iconproducts-icon--chevron"', compact)

    def test_products_template_offsets_arrow_wraps_inside_viewport(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn(".carousel-arrow-wrap.left{", compact)
        self.assertIn("left:6px", compact)
        self.assertIn(".carousel-arrow-wrap.right{", compact)
        self.assertIn("right:6px", compact)
        self.assertNotIn("left:-20px", compact)
        self.assertNotIn("right:-20px", compact)

    def test_products_template_uses_click_cursor_for_cart_button(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn(".cart-icon{", compact)
        self.assertIn("cursor:pointer", compact)

    def test_products_template_reduces_main_price_font_size(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn(".new-price{", compact)
        self.assertIn("font-size:36px", compact)
        self.assertIn("@media(max-width:930px)", compact)
        self.assertIn("font-size:30px", compact)
        self.assertIn("@media(max-width:620px)", compact)
        self.assertIn("font-size:20px", compact)

    def test_products_template_has_cart_modal_layout(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('id="products-cart-modal"', template_text)
        self.assertIn('class="cart-modal-overlay"', template_text)
        self.assertIn('id="products-cart-items"', template_text)
        self.assertIn('id="products-cart-total"', template_text)
        self.assertIn('id="products-cart-close"', template_text)
        self.assertIn("toggleCartModal", template_text)
        self.assertIn("renderCartModal", template_text)
        self.assertIn("CART_ITEMS_KEY", template_text)
        self.assertIn("data-action=\"cart-decrease\"", template_text)
        self.assertIn("data-action=\"cart-increase\"", template_text)

    def test_products_template_hides_debug_log_panel(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertNotIn('id="products-debug-log"', template_text)
        self.assertNotIn('id="products-debug-copy"', template_text)
        self.assertNotIn("Debug logs", template_text)

    def test_products_template_has_mobile_toolbar_layout(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn("@media(max-width:620px)", compact)
        self.assertIn("grid-template-columns:120px1fr48px", compact)
        self.assertIn("flex:0058vw", compact)
        self.assertIn("max-width:220px", compact)

    def test_products_template_uses_single_svg_icon_set(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('class="products-icon products-icon--search"', template_text)
        self.assertIn('class="products-icon products-icon--cart"', template_text)
        self.assertIn('class="products-icon products-icon--truck"', template_text)
        self.assertIn('class="products-icon products-icon--headset"', template_text)

    def test_products_template_renders_out_of_stock_state(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("Уточнить наличие", template_text)
        self.assertIn("add-to-cart-button--ghost", template_text)
        self.assertIn("disabled", template_text)

    def test_products_template_uses_subject_based_cart_tool_flow(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("callTool", template_text)
        self.assertIn("add_to_my_cart", template_text)
        self.assertIn("discount_price", template_text)
        self.assertIn("manufacturer", template_text)
        self.assertNotIn("CART_SESSION_KEY", template_text)
        self.assertNotIn("CART_TOKEN_KEY", template_text)
        self.assertNotIn("Authorization", template_text)
        self.assertNotIn("cart/add", template_text)

    def test_products_template_sends_add_to_cart_without_waiting_backend_response(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("const callAddToMyCart = (product) =>", template_text)
        self.assertIn("Promise.resolve(callAddToMyCart(product))", template_text)
        self.assertIn("syncLocalCartFromToolPayload(result)", template_text)
        self.assertIn("const callSetCartItemQuantity = () =>", template_text)
        self.assertIn('window.openai.callTool("add_to_my_cart", { items: payloadItems })', template_text)
        self.assertIn('debugLog("add_to_cart_click"', template_text)
        self.assertIn('debugLog("call_add_to_my_cart_start"', template_text)
        self.assertIn('debugLog("call_add_to_my_cart_error"', template_text)

    def test_products_template_uses_safe_storage_fallback_for_cart_flow(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("const memoryStorage = Object.create(null);", template_text)
        self.assertIn("const readStorageValue = (key) =>", template_text)
        self.assertIn("const writeStorageValue = (key, value) =>", template_text)
        self.assertNotIn("readStorageValue(CART_SESSION_KEY)", template_text)

    def test_products_template_cart_modal_uses_local_cart_even_without_saved_item_meta(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("const fromProductsState = state.products.find((entry) => entry.id === productId)", template_text)
        self.assertIn("const item = (cartItems[productId] && typeof cartItems[productId] === \"object\"", template_text)
        self.assertIn("name: normalizeText(item.name) || `Товар #${productId}`", template_text)

    def test_products_template_syncs_local_cart_from_tool_payload(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("applyCartSnapshot", template_text)
        self.assertIn("syncLocalCartFromToolPayload", template_text)
        self.assertIn("isCartSnapshotCandidate", template_text)
        self.assertIn("hasCartItemStructure", template_text)
        self.assertIn("candidate.cart_session_id", template_text)
        self.assertIn("candidate.cart?.items", template_text)
        self.assertIn("writeLocalCart(", template_text)
        self.assertIn("renderCartBadge()", template_text)

    def test_products_template_bootstraps_local_cart_storage(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("ensureLocalCartBootstrap", template_text)
        self.assertIn("bootstrapCartFromBackend", template_text)
        self.assertIn('window.openai.callTool("my_cart", {})', template_text)
        self.assertIn("Promise.resolve(bootstrapCartFromBackend())", template_text)
        self.assertIn("writeStorageValue(LOCAL_CART_KEY", template_text)
        self.assertIn("writeStorageValue(CART_ITEMS_KEY", template_text)
        self.assertIn("LOCAL_CART_SESSION_ID_KEY", template_text)
        self.assertIn("readStoredCartSessionId", template_text)
        self.assertIn("writeStoredCartSessionId", template_text)
        self.assertIn("clearLocalCartState", template_text)
        self.assertIn("storedSessionId !== nextSessionId", template_text)

    def test_products_template_uses_add_endpoint_for_card_add_only(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("use_add_endpoint: true", template_text)
        self.assertIn('window.openai.callTool("add_to_my_cart", payload)', template_text)

    def test_products_template_uses_loading_blur_overlay(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn("is-loading", template_text)
        self.assertIn("products-loading-overlay", template_text)
        self.assertIn("backdrop-filter", template_text)
        self.assertIn("products-loading-spinner", template_text)
        self.assertIn("skeleton-card", template_text)
        self.assertIn("min-height: 430px", template_text)

    def test_products_template_does_not_seed_static_cards(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertNotIn("Аспирин плюс с, таб шип 400/240мг, N2x10", template_text)
        self.assertNotIn("Bayer Consumer Care", template_text)

    def test_products_template_increases_product_image_zone(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertIn("height:210px", compact)
        self.assertIn("object-fit:contain", compact)


if __name__ == "__main__":
    unittest.main()
