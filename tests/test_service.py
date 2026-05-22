import sqlite3

from sneakers.config import load_config
from sneakers.db import get_sighting, upsert_sighting
from sneakers.models import RawProduct
from sneakers.service import alert_reason, fetch_with_retries, format_alert, is_australian_result, scan_source, search_products


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


def test_alert_reason_detects_first_sighting():
    current = RawProduct("nike_au", "Ja Morant AF1", "https://example.test/1")

    assert alert_reason(None, current) == "new_sighting"


def test_alert_reason_ignores_unchanged_existing_sighting(db_conn):
    existing = upsert_sighting(
        conn=db_conn,
        product_sku="IQ9773-400",
        retailer_id="nike_au",
        product_url="https://example.test/1",
        title="Ja Morant AF1",
        sku_found="IQ9773-400",
        current_price=170.0,
        original_price=170.0,
        currency="AUD",
        is_discounted=False,
        availability="available",
    )
    current = RawProduct(
        "nike_au",
        "Ja Morant AF1",
        "https://example.test/1",
        current_price=170.0,
        original_price=170.0,
        availability="available",
    )

    assert alert_reason(existing, current) is None


def test_alert_reason_detects_price_drop(db_conn):
    existing = upsert_sighting(
        conn=db_conn,
        product_sku="IQ9773-400",
        retailer_id="nike_au",
        product_url="https://example.test/1",
        title="Ja Morant AF1",
        sku_found="IQ9773-400",
        current_price=170.0,
        original_price=170.0,
        currency="AUD",
        is_discounted=False,
    )
    current = RawProduct(
        "nike_au",
        "Ja Morant AF1",
        "https://example.test/1",
        current_price=120.0,
        original_price=170.0,
    )

    assert alert_reason(existing, current) == "price_drop"


def test_alert_reason_detects_available_transition(db_conn):
    existing = upsert_sighting(
        conn=db_conn,
        product_sku="IQ9773-400",
        retailer_id="nike_au",
        product_url="https://example.test/1",
        title="Ja Morant AF1",
        sku_found="IQ9773-400",
        current_price=None,
        original_price=None,
        currency="AUD",
        is_discounted=False,
        availability="possible",
    )
    current = RawProduct("nike_au", "Ja Morant AF1", "https://example.test/1", availability="available")

    assert alert_reason(existing, current) == "available_now"


def test_scan_source_marks_alerted_when_alert_sent(monkeypatch, db_conn):
    config = load_config("config/products.yaml")
    product = config.products[0]
    source = next(source for source in config.sources if source.id == "nike_au")

    monkeypatch.setattr("sneakers.service.fetch_source_html", lambda source, url, settings: "<html></html>")
    monkeypatch.setattr(
        "sneakers.service.parse_source",
        lambda source, url, html: [
            RawProduct(
                retailer_id="nike_au",
                title="Ja Morant Air Force 1 Denim IQ9773-400",
                url="https://nike.test/product/1",
                current_price=170.0,
                original_price=170.0,
                availability="available",
            )
        ],
    )

    hits = scan_source(db_conn, config, product, source, "https://nike.test/search")

    assert hits[0]["alert_reason"] == "new_sighting"
    assert hits[0]["match_confidence"] == "high"
    sighting = get_sighting(db_conn, product.sku, source.id, "https://nike.test/product/1")
    assert sighting.last_alerted_at is not None


def test_fetch_with_retries_attempts_until_success(monkeypatch):
    config = load_config("config/products.yaml")
    source = next(source for source in config.sources if source.id == "nike_au")
    attempts = {"count": 0}

    def flaky_fetch(source, url, settings):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary")
        return "<html>ok</html>"

    monkeypatch.setattr("sneakers.service.fetch_source_html", flaky_fetch)
    monkeypatch.setattr("sneakers.service.time.sleep", lambda seconds: None)
    config.settings.retry_attempts = 2
    config.settings.retry_backoff_seconds = 0

    html = fetch_with_retries(source, "https://nike.test", config.settings)

    assert html == "<html>ok</html>"
    assert attempts["count"] == 2
