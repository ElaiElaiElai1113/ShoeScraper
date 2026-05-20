import sqlite3

from sneakers.config import load_config
from sneakers.models import RawProduct
from sneakers.service import format_alert, is_australian_result, search_products


def test_search_products_filters_by_source_type(monkeypatch):
    config = load_config("config/products.yaml")

    def fake_fetch(source, url, settings):
        if source.id == "ebay_au":
            return """
            <li>
              <a href="https://www.ebay.com.au/itm/1">Ja Morant Air Force 1 Denim IQ9773-400</a>
              <span>AU $90.00</span>
            </li>
            """
        return """
        <article>
          <a href="/p/1">Ja Morant Air Force 1 Denim IQ9773-400</a>
          <span>$170.00</span>
        </article>
        """

    monkeypatch.setattr("sneakers.service.fetch_source_html", fake_fetch)

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    results = search_products(
        config=config,
        conn=conn,
        query="IQ9773-400",
        source_type="second_hand",
        source_ids=["ebay_au", "nike_au"],
    )

    assert [result["retailer_id"] for result in results] == ["ebay_au"]
    assert results[0]["condition_type"] == "second_hand"


def test_format_alert_includes_marketplace_details():
    alert = format_alert({
        "product": "Jordan 9 Retro Wheat",
        "sku": "AR4491-700",
        "retailer": "eBay AU",
        "source_type": "second_hand",
        "condition_type": "second_hand",
        "title": "Jordan 9 Retro Wheat US10",
        "url": "https://www.ebay.com.au/itm/123",
        "prices": [120.0],
        "location": "Sydney, NSW",
        "availability": "available",
    })

    assert "Source: second_hand" in alert
    assert "Location: Sydney, NSW" in alert
    assert "Price: $120.00" in alert


def test_australia_filter_accepts_aud_or_state_locations():
    assert is_australian_result(RawProduct("ebay_au", "Sideshow Gambit", "https://example.test", currency="AUD"))
    assert is_australian_result(
        RawProduct("facebook_marketplace", "Sideshow Gambit", "https://example.test", location="Melbourne, VIC")
    )


def test_australia_filter_rejects_obvious_non_au_marketplace_results():
    assert not is_australian_result(
        RawProduct("ebay_au", "Sideshow Gambit", "https://example.test", currency="USD")
    )
    assert not is_australian_result(
        RawProduct("facebook_marketplace", "Sideshow Gambit", "https://example.test", location="Los Angeles, CA")
    )
