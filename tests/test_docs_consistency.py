from pathlib import Path
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

    def test_faq_doc_has_current_default_match_count(self) -> None:
        content = self._read("docs/features/faq.md")
        self.assertIn("FAQ_MATCH_COUNT_DEFAULT", content)
        self.assertIn("по умолчанию `5`", content)


if __name__ == "__main__":
    unittest.main()
