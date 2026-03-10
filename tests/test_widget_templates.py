"""Tests for static widget template mocks."""

from __future__ import annotations

from pathlib import Path
import re
import unittest


class WidgetTemplateTests(unittest.TestCase):

    @staticmethod
    def _read_products_bundle_text() -> str:
        html_path = Path("app/widgets/products.html")
        html_text = html_path.read_text(encoding="utf-8")
        bundle_parts = [html_text]

        css_paths = [
            match
            for match in re.findall(r'href="(\./styles/[^"]+\.css)"', html_text)
            if match.startswith("./styles/")
        ]
        for css_rel_path in css_paths:
            css_path = html_path.parent / css_rel_path.removeprefix("./")
            bundle_parts.append(css_path.read_text(encoding="utf-8"))

        js_paths = [
            match
            for match in re.findall(r'src="(\./scripts/[^"]+\.js)"', html_text)
            if match.startswith("./scripts/")
        ]
        for js_rel_path in js_paths:
            js_path = html_path.parent / js_rel_path.removeprefix("./")
            bundle_parts.append(js_path.read_text(encoding="utf-8"))

        return "\n".join(bundle_parts)

    @staticmethod
    def _read_my_cart_bundle_text() -> str:
        html_path = Path("app/widgets/my-cart.html")
        html_text = html_path.read_text(encoding="utf-8")
        bundle_parts = [html_text]

        css_paths = [
            match
            for match in re.findall(r'href="(\./styles/[^"]+\.css)"', html_text)
            if match.startswith("./styles/")
        ]
        for css_rel_path in css_paths:
            css_path = html_path.parent / css_rel_path.removeprefix("./")
            bundle_parts.append(css_path.read_text(encoding="utf-8"))

        js_paths = [
            match
            for match in re.findall(r'src="(\./scripts/[^"]+\.js)"', html_text)
            if match.startswith("./scripts/")
        ]
        for js_rel_path in js_paths:
            js_path = html_path.parent / js_rel_path.removeprefix("./")
            bundle_parts.append(js_path.read_text(encoding="utf-8"))

        return "\n".join(bundle_parts)

    def test_all_tool_templates_exist(self) -> None:
        widget_dir = Path("app/widgets")
        expected_templates = {
            "products.html",
            "my-cart.html",
        }
        existing_templates = {path.name for path in widget_dir.glob("*.html")}
        for template_name in expected_templates:
            self.assertIn(template_name, existing_templates)

    def test_templates_use_shared_mock_layout_shell(self) -> None:
        widget_dir = Path("app/widgets")
        template_names = (
            "products.html",
            "my-cart.html",
        )
        for template_name in template_names:
            template_text = (widget_dir / template_name).read_text(encoding="utf-8")
            if template_name == "products.html":
                self.assertNotIn("tailwind.css", template_text)
            else:
                self.assertNotIn("tailwind.css", template_text)
            self.assertIn("data-widget-shell=", template_text)
            self.assertIn("x-data=", template_text)
            self.assertIn("alpinejs", template_text)

    def test_products_template_matches_search_mock_layout(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('class="search-toolbar"', template_text)
        self.assertIn('class="product-carousel"', template_text)
        self.assertIn('class="product-card"', template_text)
        self.assertIn('class="carousel-arrow left"', template_text)
        self.assertIn('class="carousel-arrow right"', template_text)

    def test_products_template_does_not_have_inline_style_fallback(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertNotIn('data-inline-widget-style="products"', template_text)

    def test_products_template_has_desktop_carousel_and_tablet_layout(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", compact)
        self.assertIn("width:calc(100%+190px)", compact)
        self.assertIn("@media(max-width:930px)", compact)
        self.assertIn("@media(max-width:620px)", compact)

    def test_products_template_has_bottom_controls(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('class="carousel-bottom"', template_text)
        self.assertIn('class="center-indicator"', template_text)
        self.assertGreaterEqual(template_text.count("center-indicator"), 2)
        self.assertIn('class="products-icon products-icon--truck"', template_text)
        self.assertIn('class="products-icon products-icon--headset"', template_text)
        self.assertIn('id="products-support-button"', template_text)
        self.assertIn('id="products-support-layer"', template_text)
        self.assertIn('id="products-support-popup"', template_text)
        self.assertIn('id="products-support-title"', template_text)
        self.assertIn('id="products-support-close"', template_text)
        self.assertIn('id="products-support-telegram"', template_text)
        self.assertIn('id="products-support-viber"', template_text)
        self.assertIn('id="products-support-facebook"', template_text)
        self.assertIn('id="products-support-phone"', template_text)
        self.assertIn("https://t.me/aptekamd_bot", template_text)
        self.assertIn("viber://pa?chatURI=aptekamd_bot", template_text)
        self.assertIn("https://www.facebook.com/aptekamd/", template_text)
        self.assertIn("tel:+37322802000", template_text)
        self.assertIn('fill="#7e57c2"', template_text)
        self.assertIn('fill="#27a6e5"', template_text)
        self.assertIn('fill="#1877f2"', template_text)
        self.assertIn('fill="#6b7280"', template_text)
        self.assertNotIn('class="section-divider"', template_text)

    def test_products_template_positions_support_bubble_near_click_source(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("ctx.actions.openSupportPopup = () =>", template_text)
        self.assertIn("const setOpen = (nextState) =>", template_text)
        self.assertIn("supportCloseButton.addEventListener(\"click\", (event) =>", template_text)
        self.assertIn("action === \"support-contact\"", template_text)
        self.assertIn('querySelectorAll(\'[data-action="support-contact"]\')', template_text)
        self.assertIn("actions.openSupportPopup(button)", template_text)
        self.assertNotIn("window.location.href = viberDeepLink", template_text)

    def test_products_template_limits_widget_height(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("align-items:flex-start", compact)
        self.assertNotIn("overflow-y:auto", compact)
        self.assertNotIn("max-height:calc(100vh-32px)", compact)

    def test_products_template_uses_external_assets(self) -> None:
        html_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        self.assertIn('href="./styles/widget-products.css"', html_text)
        self.assertIn('src="./scripts/state.js"', html_text)
        self.assertIn('src="./scripts/products-render.js"', html_text)
        self.assertIn('src="./scripts/products-tools.js"', html_text)
        self.assertIn('src="./scripts/products-support.js"', html_text)
        self.assertIn('src="./scripts/products-toast.js"', html_text)
        self.assertIn('src="./scripts/products.js"', html_text)
        template_text = self._read_products_bundle_text()
        self.assertNotIn("<style>", template_text)
        self.assertNotIn("<script>", template_text)

    def test_my_cart_template_uses_external_assets(self) -> None:
        html_text = Path("app/widgets/my-cart.html").read_text(encoding="utf-8")
        self.assertIn('href="./styles/widget-my-cart.css"', html_text)
        self.assertIn('src="./scripts/my-cart-state.js"', html_text)
        self.assertIn('src="./scripts/my-cart-render.js"', html_text)
        self.assertIn('src="./scripts/my-cart.js"', html_text)
        template_text = self._read_my_cart_bundle_text()
        self.assertNotIn("<style>", template_text)
        self.assertNotIn("<script>", template_text)

    def test_products_widget_assets_exist(self) -> None:
        self.assertTrue(Path("app/widgets/styles/widget-products.css").exists())
        self.assertTrue(Path("app/widgets/scripts/state.js").exists())
        self.assertTrue(Path("app/widgets/scripts/products-render.js").exists())
        self.assertTrue(Path("app/widgets/scripts/products-tools.js").exists())
        self.assertTrue(Path("app/widgets/scripts/products-support.js").exists())
        self.assertTrue(Path("app/widgets/scripts/products-toast.js").exists())
        self.assertTrue(Path("app/widgets/scripts/products.js").exists())

    def test_my_cart_widget_assets_exist(self) -> None:
        self.assertTrue(Path("app/widgets/styles/widget-my-cart.css").exists())
        self.assertTrue(Path("app/widgets/scripts/my-cart-state.js").exists())
        self.assertTrue(Path("app/widgets/scripts/my-cart-render.js").exists())
        self.assertTrue(Path("app/widgets/scripts/my-cart.js").exists())

    def test_legacy_cart_templates_are_removed(self) -> None:
        self.assertFalse(Path("app/widgets/add-to-my-cart.html").exists())
        self.assertFalse(Path("app/widgets/checkout.html").exists())
        self.assertFalse(Path("app/widgets/faq.html").exists())
        self.assertFalse(Path("app/widgets/theme.html").exists())
        self.assertFalse(Path("app/widgets/tracking.html").exists())

    def test_widget_shell_script_supports_back_navigation(self) -> None:
        script_text = Path("app/widgets/scripts/widget-shell.js").read_text(encoding="utf-8")
        self.assertIn('const NAV_BACK_STORAGE_KEY = "apteka_widget_nav_back_map";', script_text)
        self.assertIn("const backButton = document.getElementById(\"widget-back-button\");", script_text)
        self.assertIn("const readBackMap = () => {", script_text)
        self.assertIn("const writeBackMap = (nextMap) => {", script_text)
        self.assertIn("const resolveBackEntry = () => {", script_text)
        self.assertIn("const openWidgetByTemplate = async (template, replacePrevious) => {", script_text)
        self.assertIn("if (typeof window.openai?.openWidget === \"function\")", script_text)
        self.assertIn("await window.openai.openWidget(template, { replace_previous: replacePrevious });", script_text)
        self.assertIn("backButton.addEventListener(\"click\", () => {", script_text)
        self.assertIn(".callTool(backEntry.tool, backEntry.arguments || {})", script_text)
        self.assertIn("backMap[nextWidgetId] = {", script_text)
        self.assertIn("delete backMap[activeWidgetId];", script_text)

    def test_products_script_uses_modular_bootstrap_layers(self) -> None:
        script_text = Path("app/widgets/scripts/products.js").read_text(encoding="utf-8")
        self.assertIn("window.ProductsState.createContext", script_text)
        self.assertIn("window.ProductsRender.attach", script_text)
        self.assertIn("window.ProductsTools.attach", script_text)
        self.assertIn("window.ProductsSupport.attach", script_text)
        self.assertIn("window.ProductsToast.attach", script_text)
        self.assertNotIn('const LOCAL_CART_KEY = "apteka_widget_cart";', script_text)

    def test_products_template_has_toast_layer_markup(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('id="products-toast-layer"', template_text)
        self.assertIn('aria-live="polite"', template_text)
        self.assertIn("products-toast-layer", template_text)
        self.assertIn("products-toast-close", template_text)
        self.assertIn("productsToastQueue", template_text)
        self.assertIn("productsToastQueue.shift()", template_text)
        self.assertIn("MAX_VISIBLE_TOASTS = 7", template_text)
        self.assertIn("activeToasts", template_text)
        self.assertIn("activeToasts.length < MAX_VISIBLE_TOASTS", template_text)
        self.assertIn("layer.append(toast)", template_text)
        self.assertIn("window.setTimeout(dismissToast", template_text)
        self.assertIn("showFromQueue()", template_text)
        self.assertIn("DEFAULT_DURATION_MS = 1300", template_text)
        self.assertIn("durationMs: Number(payload?.durationMs) > 0 ? Number(payload.durationMs) : DEFAULT_DURATION_MS", template_text)
        self.assertIn("document.body.append(layer)", template_text)
        self.assertNotIn("ResizeObserver", template_text)
        self.assertNotIn("canRenderAnotherToast", template_text)

    def test_products_template_positions_toast_left_of_cart_button(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertNotIn("cartRect.left", template_text)
        self.assertIn('layer.style.left = "8px"', template_text)
        self.assertIn('layer.style.right = "auto"', template_text)
        self.assertIn("layer.style.width =", template_text)
        self.assertIn('layer.style.top = "4px"', template_text)
        self.assertIn('window.addEventListener("resize", positionLayer)', template_text)
        self.assertIn('window.addEventListener("scroll", positionLayer, { passive: true })', template_text)
        self.assertIn("window.setTimeout(positionLayer, 0)", template_text)

    def test_products_template_uses_compact_toast_dimensions(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("top:4px", compact)
        self.assertIn("left:8px", compact)
        self.assertIn("right:auto", compact)
        self.assertIn("width:min(264px,calc(100vw-24px))", compact)
        self.assertIn("z-index:2147483647", compact)
        self.assertIn("overflow:visible", compact)
        self.assertIn("padding:8px10px10px", compact)
        self.assertIn("font-size:18px", compact)
        self.assertIn("font-size:14px", compact)
        self.assertIn(".products-toast-status{", compact)
        self.assertIn("min-width:0", compact)
        self.assertIn("flex:1", compact)
        self.assertIn(".products-toast-status>span:last-child{", compact)
        self.assertIn("text-overflow:ellipsis", compact)
        self.assertIn("white-space:nowrap", compact)
        self.assertIn(".products-toast-close{", compact)
        self.assertIn("flex:00auto", compact)

    def test_products_template_shows_toast_immediately_on_add_click(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("ctx.toast.enqueue({", template_text)
        self.assertIn('title: "Успешно"', template_text)
        self.assertIn("toast.classList.add(\"is-visible\")", template_text)
        self.assertNotIn("window.requestAnimationFrame", template_text)

        add_to_cart_start = template_text.find("const addToCart = (productId) => {")
        enqueue_pos = template_text.find("ctx.toast.enqueue({", add_to_cart_start)
        write_local_cart_pos = template_text.find("writeLocalCartAdd(productId);", add_to_cart_start)
        self.assertGreater(enqueue_pos, add_to_cart_start)
        self.assertGreater(write_local_cart_pos, add_to_cart_start)
        self.assertLess(enqueue_pos, write_local_cart_pos)

    def test_products_template_uses_clickable_official_logo(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('href="https://www.apteka.md/"', template_text)
        self.assertIn('class="search-logo-image"', template_text)
        self.assertIn(
            'src="https://www.apteka.md/_next/static/media/BigLogo.50692667.svg"',
            template_text,
        )

    def test_products_template_removes_top_labels_and_shell_card(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertNotIn("Вызываемый инструмент", template_text)
        self.assertNotIn('class="brand-row"', template_text)
        self.assertNotIn("Найдено товаров:", template_text)

    def test_products_template_uses_transparent_background(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("background:transparent", compact)
        self.assertNotIn("background:#1a1d23", compact)

    def test_products_template_calls_search_tool(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('window.openai.callTool("search_products"', template_text)
        self.assertNotIn("https://stage.apteka.md/api/v1/front/search", template_text)
        self.assertIn("localStorage", template_text)
        self.assertIn("api_base_url", template_text)
        self.assertNotIn('|| "аспирин"', template_text)
        self.assertNotIn("renderProducts();\n        searchProducts(", template_text)

    def test_products_template_reads_initial_tool_payload_before_manual_search(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const extractInitialToolPayload", template_text)
        self.assertIn("window.openai", template_text)
        self.assertIn("INITIAL_PAYLOAD_WAIT_MS", template_text)
        self.assertIn("window.addEventListener(\"message\",", template_text)
        self.assertIn("window.setInterval", template_text)

    def test_products_template_has_interactive_carousel_track(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('class="product-track"', template_text)
        self.assertIn('class="carousel-arrow-wrap left"', template_text)
        self.assertIn('class="carousel-arrow-wrap right"', template_text)
        self.assertIn('class="carousel-arrow left"', template_text)
        self.assertIn('class="carousel-arrow right"', template_text)
        self.assertIn("scrollBy", template_text)
        self.assertIn('target.closest("[data-action]")', template_text)
        self.assertIn("target instanceof Element ? target.closest", template_text)
        self.assertIn("target?.parentElement?.closest", template_text)
        self.assertIn("event.composedPath", template_text)
        self.assertIn('querySelectorAll(\'[data-action="add-to-cart"]\')', template_text)

    def test_products_template_normalizes_product_image_urls(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const resolveImageUrl", template_text)
        self.assertIn("new URL(imageUrl, baseUrl)", template_text)
        self.assertIn("const getFallbackImage", template_text)
        self.assertIn('"/assets/images/placeholder-600x600.png"', template_text)
        self.assertNotIn("https://api.apteka.md/assets/images/placeholder-600x600.png", template_text)

    def test_products_template_maps_name_from_ru_ro_fields(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("normalizeText(item.name_ru)", template_text)
        self.assertIn("normalizeText(item.name_ro)", template_text)

    def test_products_template_uses_fixed_card_content_zones(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("display: grid;", template_text)
        self.assertIn("grid-template-rows: 210px", template_text)
        self.assertIn("line-clamp", template_text)
        self.assertIn("product-price-row", template_text)
        self.assertIn("product-manufacturer-row", template_text)

    def test_products_template_uses_non_overlay_arrow_wraps(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("background:transparent", compact)
        self.assertIn("width:34px", compact)
        self.assertIn("height:86px", compact)
        self.assertIn("border-radius:18px", compact)
        self.assertIn("backdrop-filter:blur(3px)", compact)
        self.assertIn('class="products-iconproducts-icon--chevron"', compact)

    def test_products_template_offsets_arrow_wraps_inside_viewport(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn(".carousel-arrow-wrap.left{", compact)
        self.assertIn("left:6px", compact)
        self.assertIn(".carousel-arrow-wrap.right{", compact)
        self.assertIn("right:6px", compact)
        self.assertNotIn("left:-20px", compact)
        self.assertNotIn("right:-20px", compact)

    def test_products_template_uses_click_cursor_for_cart_button(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn(".cart-icon{", compact)
        self.assertIn("cursor:pointer", compact)

    def test_products_template_reduces_main_price_font_size(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn(".new-price{", compact)
        self.assertIn("font-size:36px", compact)
        self.assertIn("@media(max-width:930px)", compact)
        self.assertIn("font-size:30px", compact)
        self.assertIn("@media(max-width:620px)", compact)
        self.assertIn("font-size:20px", compact)

    def test_products_template_has_cart_modal_layout(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('id="products-cart-modal"', template_text)
        self.assertIn('class="cart-modal-overlay"', template_text)
        self.assertIn('id="products-cart-items"', template_text)
        self.assertIn('id="products-cart-total"', template_text)
        self.assertIn('id="products-cart-close"', template_text)
        self.assertIn("toggleCartModal", template_text)
        self.assertIn("renderCartModal", template_text)
        self.assertIn("CART_ITEMS_KEY", template_text)
        self.assertIn('decrease.dataset.action = "cart-decrease"', template_text)
        self.assertIn('increase.dataset.action = "cart-increase"', template_text)
        self.assertIn('remove.dataset.action = "cart-remove"', template_text)
        self.assertIn('remove.setAttribute("aria-label",', template_text)
        self.assertIn('id="products-go-to-cart-button"', template_text)
        self.assertIn('id="products-checkout-button"', template_text)

    def test_products_template_renders_cart_modal_without_innerhtml_for_items(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertNotIn(
            "cartModalItems.innerHTML = '<p class=\"cart-modal-empty\">В корзине пока нет товаров</p>';",
            template_text,
        )
        self.assertNotIn("cartModalItems.innerHTML = rows", template_text)
        self.assertIn("document.createElement(\"article\")", template_text)

    def test_products_template_hides_debug_log_panel(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertNotIn('id="products-debug-log"', template_text)
        self.assertNotIn('id="products-debug-copy"', template_text)
        self.assertNotIn("Debug logs", template_text)

    def test_products_template_has_mobile_toolbar_layout(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("@media(max-width:620px)", compact)
        self.assertIn("grid-template-columns:120px1fr48px", compact)
        self.assertIn("flex:0058vw", compact)
        self.assertIn("max-width:220px", compact)
        self.assertIn(".products-support-popup{", compact)
        self.assertIn("width:min(390px,calc(100vw-24px))", compact)
        self.assertIn("border-radius:8px", compact)
        self.assertIn("pointer-events:auto", compact)

    def test_products_template_uses_single_svg_icon_set(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('class="products-icon products-icon--search"', template_text)
        self.assertIn('class="products-icon products-icon--cart"', template_text)
        self.assertIn('class="products-icon products-icon--truck"', template_text)
        self.assertIn('class="products-icon products-icon--headset"', template_text)

    def test_products_template_renders_out_of_stock_state(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("Уточнить наличие", template_text)
        self.assertIn("add-to-cart-button--ghost", template_text)
        self.assertIn('data-action="support-contact"', template_text)
        self.assertNotIn('add-to-cart-button add-to-cart-button--ghost" disabled', template_text)

    def test_products_template_uses_subject_based_cart_tool_flow(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("callTool", template_text)
        self.assertIn("add_to_my_cart", template_text)
        self.assertIn("discount_price", template_text)
        self.assertIn("manufacturer", template_text)
        self.assertNotIn("CART_SESSION_KEY", template_text)
        self.assertNotIn("CART_TOKEN_KEY", template_text)
        self.assertNotIn("Authorization", template_text)
        self.assertNotIn("cart/add", template_text)

    def test_products_template_sends_add_to_cart_without_waiting_backend_response(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const callAddToMyCart = (product) =>", template_text)
        self.assertIn("enqueueCartSync(() => callAddToMyCart(product))", template_text)
        self.assertIn("state.cartSyncQueue = state.cartSyncQueue.catch(() => null).then(run)", template_text)
        self.assertIn("const callSetCartItemQuantity = () =>", template_text)
        self.assertIn("const payload = {", template_text)
        self.assertIn("items: payloadItems,", template_text)
        self.assertIn('window.openai.callTool("add_to_my_cart", payload)', template_text)
        self.assertIn("image_url: normalizeText(product?.imageUrl) || undefined", template_text)
        self.assertIn("image_url: normalizeText(itemMeta?.imageUrl) || undefined", template_text)
        self.assertIn('debugLog("add_to_cart_click"', template_text)
        self.assertIn('debugLog("call_add_to_my_cart_start"', template_text)
        self.assertIn('debugLog("call_add_to_my_cart_error"', template_text)
        self.assertIn("const escapeHtml = (value) =>", template_text)
        self.assertIn("replaceAll(\"<\", \"&lt;\")", template_text)
        self.assertIn("replaceAll(\">\", \"&gt;\")", template_text)

    def test_products_template_cart_modal_updates_via_update_payload_with_meta(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const callSetCartItemQuantity = () =>", template_text)
        self.assertIn('window.openai.callTool("add_to_my_cart", payload)', template_text)
        self.assertIn("cart_session_id: cartSessionId || undefined", template_text)
        self.assertIn("if (action === \"cart-increase\")", template_text)
        self.assertIn("if (action === \"cart-decrease\")", template_text)
        self.assertIn("if (action === \"cart-remove\")", template_text)
        self.assertIn("writeLocalCart(payload);", template_text)
        self.assertIn("enqueueCartSync(() => callSetCartItemQuantity())", template_text)

    def test_products_template_blocks_checkout_when_cart_is_empty_or_below_30_mdl(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const MIN_CHECKOUT_TOTAL_MDL = 30;", template_text)
        self.assertIn("const { total, count } = ui.getCartSummary();", template_text)
        self.assertIn("if (count <= 0)", template_text)
        self.assertIn("if (total < MIN_CHECKOUT_TOTAL_MDL)", template_text)
        self.assertIn("У вас пустая корзина", template_text)
        self.assertIn("Минимальная сумма заказа 30 mdl", template_text)
        self.assertIn('openWidgetByTemplate("ui://widget/products.html", "checkout_order", {', template_text)

    def test_products_template_cart_modal_routes_inside_single_widget(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const openWidgetByTemplate = async (template, fallbackTool, fallbackArgs) => {", template_text)
        self.assertIn("const hasOpenWidget = typeof openaiApi?.openWidget === \"function\";", template_text)
        self.assertIn("const hasCallTool = typeof openaiApi?.callTool === \"function\";", template_text)
        self.assertIn('id="products-page-my-cart"', template_text)
        self.assertIn('id="products-page-checkout"', template_text)
        self.assertIn('id="products-page-search"', template_text)
        self.assertIn('id="products-back-from-my-cart"', template_text)
        self.assertIn('id="products-back-from-checkout"', template_text)
        self.assertIn("const showInternalPage = (pageName) => {", template_text)
        self.assertIn("showInternalPage(\"my-cart\")", template_text)
        self.assertIn("showInternalPage(\"checkout\")", template_text)
        self.assertIn("if (!hasOpenWidget)", template_text)
        self.assertIn("via: \"internal-router\"", template_text)
        self.assertIn("const fallbackToolName = normalizeText(fallbackTool);", template_text)
        self.assertIn("const toolResult = await openaiApi.callTool(fallbackToolName, fallbackArgs || {});", template_text)
        self.assertIn("const fallbackTemplate = normalizeText(structuredPayload?.widget?.open?.template);", template_text)
        self.assertIn("if (!hasCallTool)", template_text)
        self.assertIn("if (hasOpenWidget)", template_text)
        self.assertNotIn("tool-no-openWidget", template_text)
        self.assertIn("const replacePrevious = structuredPayload?.widget?.open?.replace_previous !== false;", template_text)
        self.assertIn("await openaiApi.openWidget(fallbackTemplate, { replace_previous: replacePrevious });", template_text)
        self.assertIn("await openaiApi.openWidget(template, { replace_previous: true });", template_text)
        self.assertIn('openWidgetByTemplate("ui://widget/my-cart.html", "my_cart", {', template_text)
        self.assertIn('openWidgetByTemplate("ui://widget/products.html", "checkout_order", {', template_text)
        self.assertIn("cart_session_id: cartSessionId || undefined", template_text)
        self.assertIn("goToCartButton.addEventListener(\"click\",", template_text)
        self.assertIn("checkoutButton.addEventListener(\"click\",", template_text)
        self.assertIn('toolPage: "my-cart"', template_text)
        self.assertIn('toolPage: "checkout"', template_text)

    def test_products_template_has_tracking_page_for_order_status(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('id="products-page-tracking"', template_text)
        self.assertIn('id="products-back-from-tracking"', template_text)
        self.assertIn('id="products-tracking-lookup"', template_text)
        self.assertIn('id="products-tracking-count"', template_text)
        self.assertIn('id="products-tracking-orders"', template_text)
        self.assertIn("renderTrackingPage", template_text)
        self.assertIn('showInternalPage("tracking")', template_text)
        self.assertIn('return "tracking";', template_text)
        self.assertIn("state.tracking = {", template_text)
        self.assertIn("orders: Array.isArray(payload.orders) ? payload.orders : []", template_text)

    def test_products_template_logs_cart_navigation_debug_events(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('debugLog("cart_navigation_click"', template_text)
        self.assertIn('debugLog("widget_open_attempt"', template_text)
        self.assertIn('debugLog("widget_open_success"', template_text)
        self.assertIn('debugLog("widget_open_fallback_tool"', template_text)
        self.assertIn('debugLog("widget_open_error"', template_text)
        self.assertIn('window.__APTEKA_WIDGET_LOGS__', template_text)

    def test_products_template_disallows_zero_price_items_in_cart(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("if (!Number.isFinite(linePrice) || linePrice <= 0)", template_text)
        self.assertIn("if (price <= 0) {", template_text)
        self.assertIn("Number.isFinite(discountPrice) && discountPrice > 0", template_text)
        self.assertIn("itemMeta.price = 0;", template_text)
        self.assertIn("itemMeta.discountPrice = 0;", template_text)
        self.assertIn("enqueueCartSync(() => callSetCartItemQuantity())", template_text)
        self.assertIn("quantity < 0", template_text)
        self.assertIn("quantity <= 0", template_text)

    def test_products_template_keeps_zero_quantity_until_sync_for_cart_remove(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("payload[productId] = 0;", template_text)
        self.assertIn("if (!Number.isFinite(quantity) || quantity <= 0)", template_text)
        self.assertIn("if (!Number.isFinite(quantity) || quantity <= 0)", template_text)

    def test_products_template_debounces_cart_quantity_sync_requests(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("let cartSyncTimerId = 0;", template_text)
        self.assertIn("window.clearTimeout(cartSyncTimerId);", template_text)
        self.assertIn("cartSyncTimerId = window.setTimeout(() => {", template_text)
        self.assertIn("scheduleCartQuantitySync();", template_text)

    def test_products_template_uses_error_toast_style_for_checkout_validation(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn('kind: "error"', template_text)
        self.assertIn("products-toast-status-icon--error", template_text)
        self.assertIn("statusIcon.textContent = payload.kind === \"error\" ? \"✕\" : \"✓\";", template_text)
        self.assertIn("background: #fff1f2", template_text)
        self.assertIn("color: #d11a2a", template_text)

    def test_products_template_uses_friendly_cart_controls_style(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("border: none", template_text)
        self.assertIn("background: transparent", template_text)
        self.assertIn("color: #1f55d6", template_text)
        self.assertIn("font-size: 32px", template_text)
        self.assertIn("font-size: 22px", template_text)
        self.assertIn("font-weight: 400", template_text)
        self.assertIn("gap: 20px", template_text)
        self.assertIn("align-self: center", template_text)
        self.assertIn("grid-template-rows: auto auto", template_text)
        self.assertIn("grid-column: 1 / 3", template_text)
        self.assertIn("grid-row: 2", template_text)
        self.assertIn("font-size: 13px", template_text)
        self.assertIn("font-weight: 500", template_text)
        self.assertIn("width: 16px", template_text)
        self.assertIn("height: 16px", template_text)
        self.assertIn("background: #9ba0ab", template_text)
        self.assertIn("content.className = \"cart-modal-item-content\";", template_text)
        self.assertIn("remove.textContent = \"✕\";", template_text)
        self.assertIn("qty.append(decrease, value, increase);", template_text)
        self.assertIn("article.append(image, content, lineTotal, qty, remove);", template_text)
        self.assertIn("decrease.setAttribute(\"aria-label\",", template_text)
        self.assertIn("increase.setAttribute(\"aria-label\",", template_text)

    def test_products_template_uses_safe_storage_fallback_for_cart_flow(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const memoryStorage = Object.create(null);", template_text)
        self.assertIn("const readStorageValue = (key) =>", template_text)
        self.assertIn("const writeStorageValue = (key, value) =>", template_text)
        self.assertNotIn("readStorageValue(CART_SESSION_KEY)", template_text)

    def test_products_template_cart_modal_uses_local_cart_even_without_saved_item_meta(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("const fromProductsState = state.products.find((entry) => entry.id === productId)", template_text)
        self.assertIn("const item = (cartItems[productId] && typeof cartItems[productId] === \"object\"", template_text)
        self.assertIn("name: normalizeText(item.name) || `Товар #${productId}`", template_text)

    def test_products_template_renders_line_total_per_cart_item(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("lineTotalText: `Итого: ${toMoney(linePrice * quantity)}`", template_text)
        self.assertIn("cart-modal-item-line-total", template_text)
        self.assertIn("lineTotal.textContent = row.lineTotalText;", template_text)

    def test_products_template_syncs_local_cart_from_tool_payload(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("applyCartSnapshot", template_text)
        self.assertIn("syncLocalCartFromToolPayload", template_text)
        self.assertIn("isCartSnapshotCandidate", template_text)
        self.assertIn("hasCartItemStructure", template_text)
        self.assertIn("candidate.cart_session_id", template_text)
        self.assertIn("candidate.cart?.items", template_text)
        self.assertIn("writeLocalCart(", template_text)
        self.assertIn("renderCartBadge()", template_text)

    def test_products_template_bootstraps_local_cart_storage(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("ensureLocalCartBootstrap", template_text)
        self.assertIn("bootstrapCartFromBackend", template_text)
        self.assertIn("ensureCartBootstrapWithRetry", template_text)
        self.assertIn("scheduleDeferredCartBootstrap", template_text)
        self.assertIn("window.setTimeout(() => {", template_text)
        self.assertIn("scheduleDeferredCartBootstrap();", template_text)
        self.assertIn('window.openai.callTool("my_cart", {', template_text)
        self.assertIn("cart_session_id: storedSessionId || undefined", template_text)
        self.assertIn("Promise.resolve(ensureCartBootstrapWithRetry())", template_text)
        self.assertNotIn("if (readLocalCartCount() <= 0)", template_text)
        self.assertIn("writeStorageValue(LOCAL_CART_KEY", template_text)
        self.assertIn("writeStorageValue(CART_ITEMS_KEY", template_text)
        self.assertIn("LOCAL_CART_SESSION_ID_KEY", template_text)
        self.assertIn("readStoredCartSessionId", template_text)
        self.assertIn("writeStoredCartSessionId", template_text)
        self.assertIn("clearLocalCartState", template_text)
        self.assertIn("storedSessionId !== nextSessionId", template_text)

    def test_products_template_uses_add_endpoint_for_card_add_only(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("use_add_endpoint: true", template_text)
        self.assertIn('window.openai.callTool("add_to_my_cart", payload)', template_text)

    def test_my_cart_template_matches_requested_layout(self) -> None:
        template_text = self._read_my_cart_bundle_text()
        self.assertIn("my-cart-shell", template_text)
        self.assertIn('class="my-cart-title"', template_text)
        self.assertIn('id="my-cart-items"', template_text)
        self.assertIn('id="my-cart-total"', template_text)
        self.assertIn('id="my-cart-back-button"', template_text)
        self.assertIn('id="my-cart-checkout-button"', template_text)
        self.assertIn("window.openai.callTool(\"my_cart\"", template_text)
        self.assertIn("window.openai.callTool(\"add_to_my_cart\"", template_text)
        self.assertIn('window.openai.openWidget("ui://widget/products.html"', template_text)
        self.assertIn('window.openai.openWidget("ui://widget/products.html", { replace_previous: true })', template_text)

    def test_my_cart_template_uses_same_widget_shell_size_as_products(self) -> None:
        template_text = self._read_my_cart_bundle_text().replace(" ", "")
        self.assertIn("width:min(100%,920px)", template_text)
        self.assertIn("padding:14px10px18px", template_text)
        self.assertIn("@media(max-width:620px)", template_text)

    def test_products_template_uses_loading_blur_overlay(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertIn("is-loading", template_text)
        self.assertIn("products-loading-overlay", template_text)
        self.assertIn("backdrop-filter", template_text)
        self.assertIn("products-loading-spinner", template_text)
        self.assertIn("skeleton-card", template_text)
        self.assertIn("min-height: 430px", template_text)

    def test_products_template_does_not_seed_static_cards(self) -> None:
        template_text = self._read_products_bundle_text()
        self.assertNotIn("Аспирин плюс с, таб шип 400/240мг, N2x10", template_text)
        self.assertNotIn("Bayer Consumer Care", template_text)

    def test_products_template_increases_product_image_zone(self) -> None:
        template_text = self._read_products_bundle_text()
        compact = template_text.replace(" ", "")
        self.assertIn("height:210px", compact)
        self.assertIn("object-fit:contain", compact)


if __name__ == "__main__":
    unittest.main()


