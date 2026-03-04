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
        self.assertIn("117.99 MDL", template_text)
        self.assertIn("-8%", template_text)
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
        self.assertNotIn('class="carousel-bottom"', template_text)
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
        self.assertIn('class="search-logo-svg"', template_text)
        self.assertIn("apteka.md", template_text)

    def test_products_template_removes_top_labels_and_shell_card(self) -> None:
        template_text = Path("app/widgets/products.html").read_text(encoding="utf-8")
        compact = template_text.replace(" ", "")
        self.assertNotIn("Вызываемый инструмент", template_text)
        self.assertNotIn('class="brand-row"', template_text)
        self.assertIn("body{", compact)
        self.assertIn("background:transparent", compact)
        self.assertIn("background:transparent", compact)
        self.assertIn("border:none", compact)
        self.assertIn("overflow-y:hidden", compact)


if __name__ == "__main__":
    unittest.main()
