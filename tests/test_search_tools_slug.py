"""Tests for search tool slug mapping."""

from __future__ import annotations

from app.interfaces.mcp.tools.search_tools import _map_product, _product_to_dict


def test_stage_product_photos_use_production_media_without_changing_api(monkeypatch):
    monkeypatch.setenv("APTEKA_BASE_URL", "https://stage.apteka.md")
    monkeypatch.setenv("APTEKA_MEDIA_BASE_URL", "https://api.apteka.md")
    product = _map_product(
        {
            "id": 1,
            "images": [
                {"full": "https://stage.apteka.md/media/253945/conversions/46891-full.webp"}
            ],
        }
    )
    assert product.image_url == "https://api.apteka.md/media/253945/conversions/46891-full.webp"
    from app.interfaces.mcp.tools.apteka_urls import build_front_url

    assert build_front_url("/order/confirm-order-by-using-mobile").startswith(
        "https://stage.apteka.md/"
    )


def test_stage_media_override_preserves_path_query_and_external_cdn(monkeypatch):
    monkeypatch.setenv("APTEKA_MEDIA_BASE_URL", "https://api.apteka.md")
    assert _map_product({"id": 1, "image_url": "/media/p.webp?width=600"}).image_url == (
        "https://api.apteka.md/media/p.webp?width=600"
    )
    assert _map_product({"id": 1, "image_url": "https://cdn.example/p.webp"}).image_url == (
        "https://cdn.example/p.webp"
    )


def test_search_tool_maps_slug_from_meta_translations() -> None:
    item = {
        "id": 20859,
        "name": "Citramon U comprimate 240 mg/30 mg/180 mg N10",
        "meta": {
            "translations": {
                "ro": {"slug": "citramon-u-comprimate-240-mg30-mg180-mg-n10-51433"},
                "ru": {"slug": "citramon-u-tab-24030180mg-n10-51433"},
            }
        },
    }

    product = _map_product(item)
    payload = _product_to_dict(product, language="ru")

    assert payload["slug_ro"] == "citramon-u-comprimate-240-mg30-mg180-mg-n10-51433"
    assert payload["slug_ru"] == "citramon-u-tab-24030180mg-n10-51433"


def test_search_tool_prefers_language_specific_name() -> None:
    item = {
        "id": 1,
        "name": "Fallback name",
        "translations": {
            "ro": {"name": "Nume romanesc"},
            "ru": {"name": "Русское название"},
        },
    }

    product = _map_product(item)

    payload_ru = _product_to_dict(product, language="ru")
    payload_ro = _product_to_dict(product, language="ro")

    assert payload_ru["name"] == "Русское название"
    assert payload_ro["name"] == "Nume romanesc"
