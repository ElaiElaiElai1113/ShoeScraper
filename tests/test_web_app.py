import sqlite3

from sneakers.config import load_config
from sneakers.db import init_db, record_scrape, upsert_sighting
from web_app import (
    can_start_scheduled_scan,
    csv_response_text,
    filtered_sightings_payload,
    health_payload,
    products_payload,
    recent_sightings_payload,
    retailers_payload,
    scheduler_status_payload,
    scan_state,
)


def test_products_payload_uses_yaml_config():
    config = load_config("config/products.yaml")

    payload = products_payload(config)

    jordan = next(product for product in payload if product["sku"] == "AR4491-700")
    assert jordan["required_sizes"] == ["10"]


def test_retailers_payload_includes_source_metadata():
    config = load_config("config/products.yaml")

    payload = retailers_payload(config)

    ebay = next(source for source in payload if source["id"] == "ebay_au")
    assert ebay["source_type"] == "second_hand"
    assert ebay["render_mode"] == "auto"


def test_recent_sightings_payload_reads_new_and_legacy_tables():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    upsert_sighting(
        conn=conn,
        product_sku="AR4491-700",
        retailer_id="ebay_au",
        product_url="https://www.ebay.com.au/itm/123",
        title="Jordan 9 Retro Wheat",
        sku_found="AR4491-700",
        current_price=120.0,
        original_price=None,
        currency="AUD",
        is_discounted=False,
        source_type="second_hand",
        condition_type="second_hand",
    )
    conn.execute(
        """
        CREATE TABLE sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retailer TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            matched_text TEXT NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "INSERT INTO sightings (retailer, url, title, matched_text) VALUES (?, ?, ?, ?)",
        ("Nike AU SKU Search [IQ9773-400]", "https://nike.test/1", "Ja Morant AF1", "matched"),
    )

    payload = recent_sightings_payload(conn)

    assert {item["title"] for item in payload} == {"Jordan 9 Retro Wheat", "Ja Morant AF1"}


def test_scheduler_status_payload_includes_scheduler_fields():
    config = load_config("config/products.yaml")
    state = {
        "running": False,
        "scheduler_next_run_at": "2026-05-22 10:00:00",
        "last_trigger_type": "scheduled",
    }

    payload = scheduler_status_payload(config, state)

    assert payload["scheduler_enabled"] is False
    assert payload["scan_interval_minutes"] == 60
    assert payload["scheduler_next_run_at"] == "2026-05-22 10:00:00"
    assert payload["last_trigger_type"] == "scheduled"


def test_scheduled_scan_does_not_start_when_scan_running():
    original = dict(scan_state)
    try:
        scan_state["running"] = True

        assert can_start_scheduled_scan() is False
    finally:
        scan_state.clear()
        scan_state.update(original)


def test_health_payload_returns_retailer_health_rows():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    record_scrape(conn, "nike_au", "https://nike.test", success=False, error_type="timeout", error_message="slow")

    payload = health_payload(conn)

    assert payload["health"][0]["retailer_id"] == "nike_au"
    assert payload["health"][0]["consecutive_failures"] == 1
    assert payload["health"][0]["last_error_type"] == "timeout"


def test_filtered_sightings_payload_filters_by_confidence(db_conn):
    upsert_sighting(
        conn=db_conn,
        product_sku="IQ9773-400",
        retailer_id="nike_au",
        product_url="https://nike.test/1",
        title="Ja Morant AF1",
        sku_found="IQ9773-400",
        current_price=170.0,
        original_price=170.0,
        currency="AUD",
        is_discounted=False,
        match_score=100,
        match_confidence="high",
        matched_terms=["IQ9773-400"],
    )

    payload = filtered_sightings_payload(db_conn, {"confidence": "high"})

    assert payload["sightings"][0]["match_confidence"] == "high"
    assert payload["sightings"][0]["matched_terms"] == ["IQ9773-400"]


def test_csv_response_text_exports_sightings():
    text = csv_response_text([
        {"title": "Ja Morant AF1", "retailer": "nike_au", "current_price": 170.0}
    ])

    assert "title,retailer,current_price" in text
    assert "Ja Morant AF1,nike_au,170.0" in text
