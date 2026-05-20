import sqlite3

from sneakers.config import load_config
from sneakers.db import init_db, upsert_sighting
from web_app import products_payload, recent_sightings_payload, retailers_payload


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
