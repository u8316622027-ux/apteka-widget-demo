from pathlib import Path
import json
import unittest


class DocsConsistencyTests(unittest.TestCase):
    def _read(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def test_architecture_doc_mentions_metrics_request_id_and_fastapi(self) -> None:
        content = self._read("docs/architecture/README.md")
        self.assertIn("GET /metrics", content)
        self.assertIn("X-Request-Id", content)
        self.assertIn("FastAPI", content)
        self.assertIn("`checkout_order` (implemented)", content)

    def test_checkout_doc_uses_current_statuses(self) -> None:
        content = self._read("docs/features/checkout.md")
        self.assertIn("pickup_confirmation_and_payment", content)
        self.assertIn("order_submitted", content)
        self.assertIn("courier_ready_for_submission", content)
        self.assertNotIn("courier_delivery_not_implemented", content)
        self.assertNotIn("pickup_ready_for_submission", content)
        self.assertNotIn("Add full submit for courier", content)

    def test_architecture_doc_uses_env_base_url_for_apteka_api(self) -> None:
        content = self._read("docs/architecture/README.md")
        self.assertIn("APTEKA_BASE_URL", content)
        self.assertIn("{APTEKA_BASE_URL}/api/v1/front/search", content)
        self.assertNotIn("https://stage.apteka.md/api/v1/front/search", content)

    def test_faq_doc_has_current_default_match_count(self) -> None:
        content = self._read("docs/features/faq.md")
        self.assertIn("FAQ_MATCH_COUNT_DEFAULT", content)
        self.assertIn("по умолчанию `5`", content)

    def test_architecture_doc_describes_frontend_stack(self) -> None:
        content = self._read("docs/architecture/README.md")
        self.assertIn("Alpine.js", content)
        self.assertIn("Tailwind CSS", content)
        self.assertIn("locally built", content)

    def test_package_json_contains_frontend_stack_dependencies_and_scripts(self) -> None:
        package_json = json.loads(Path("package.json").read_text(encoding="utf-8-sig"))
        scripts = package_json.get("scripts", {})
        dependencies = package_json.get("dependencies", {})
        dev_dependencies = package_json.get("devDependencies", {})

        self.assertIn("tw:build", scripts)
        self.assertIn("tw:watch", scripts)
        self.assertIn("alpinejs", dependencies)
        self.assertIn("tailwindcss", dev_dependencies)

    def test_frontend_docs_include_standards_and_decisions_index(self) -> None:
        standards = self._read("docs/frontend/standards.md")
        decisions_index = self._read("docs/frontend/decisions/README.md")

        self.assertIn("No inline CSS/JS", standards)
        self.assertIn("Accessibility minimum", standards)
        self.assertIn("320px", standards)
        self.assertIn("768px", standards)
        self.assertIn("1280px", standards)
        self.assertIn("Dependency gate", standards)
        self.assertIn("text/html;profile=mcp-app", standards)
        self.assertIn("self-contained", standards)
        self.assertIn("docs/frontend/decisions/", decisions_index)

    def test_architecture_doc_links_frontend_and_backend_docs(self) -> None:
        content = self._read("docs/architecture/README.md")
        self.assertIn("docs/frontend/standards.md", content)
        self.assertIn("docs/backend/README.md", content)

    def test_architecture_doc_describes_single_products_widget_routing(self) -> None:
        content = self._read("docs/architecture/README.md")
        self.assertIn("`ui://widget/products.html`", content)
        self.assertIn("`track_order_status_ui` открывает внутреннюю страницу `tracking`", content)
        self.assertIn("`my_cart`", content)
        self.assertIn("`support_knowledge_search` и `set_widget_theme` работают без отдельного widget template", content)


if __name__ == "__main__":
    unittest.main()
