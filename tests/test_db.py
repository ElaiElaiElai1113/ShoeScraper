from sneakers.db import (
    init_db,
    get_sighting,
    upsert_sighting,
    mark_alerted,
    record_scrape,
    get_retailer_health,
)


class TestSchemaInit:
    def test_creates_tables(self, db_conn):
        tables = {
            row[0]
            for row in db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "products_seen" in tables
        assert "scrape_log" in tables
        assert "retailer_health" in tables

    def test_idempotent(self, db_conn):
        init_db(db_conn)  # second call should not error
        tables = {
            row[0]
            for row in db_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "products_seen" in tables


class TestSightingCRUD:
    def test_insert_and_retrieve(self, db_conn):
        sighting = upsert_sighting(
            conn=db_conn,
            product_sku="IQ9773-400",
            retailer_id="nike_au",
            product_url="https://nike.com/au/product/123",
            title="Ja Morant AF1 Denim",
            sku_found="IQ9773-400",
            current_price=170.0,
            original_price=170.0,
            currency="AUD",
            is_discounted=False,
        )
        assert sighting is not None
        assert sighting.product_sku == "IQ9773-400"
        assert sighting.title == "Ja Morant AF1 Denim"
        assert sighting.is_discounted is False

    def test_insert_marketplace_fields(self, db_conn):
        sighting = upsert_sighting(
            conn=db_conn,
            product_sku="AR4491-700",
            retailer_id="ebay_au",
            product_url="https://www.ebay.com.au/itm/123",
            title="Jordan 9 Retro Wheat US10",
            sku_found="AR4491-700",
            current_price=120.0,
            original_price=None,
            currency="AUD",
            is_discounted=False,
            source_type="second_hand",
            condition_type="second_hand",
            image_url="https://img.example/jordan.jpg",
            location="Sydney, NSW",
            availability="available",
        )

        assert sighting.source_type == "second_hand"
        assert sighting.condition_type == "second_hand"
        assert sighting.image_url == "https://img.example/jordan.jpg"
        assert sighting.location == "Sydney, NSW"
        assert sighting.availability == "available"

    def test_get_sighting_not_found(self, db_conn):
        result = get_sighting(db_conn, "FAKE-SKU", "nike_au", "https://fake.url")
        assert result is None

    def test_upsert_updates_existing(self, db_conn):
        upsert_sighting(
            conn=db_conn,
            product_sku="IQ9773-400",
            retailer_id="nike_au",
            product_url="https://nike.com/au/product/123",
            title="Ja Morant AF1 Denim",
            sku_found="IQ9773-400",
            current_price=170.0,
            original_price=170.0,
            currency="AUD",
            is_discounted=False,
        )

        # Price drops
        updated = upsert_sighting(
            conn=db_conn,
            product_sku="IQ9773-400",
            retailer_id="nike_au",
            product_url="https://nike.com/au/product/123",
            title="Ja Morant AF1 Denim",
            sku_found="IQ9773-400",
            current_price=119.0,
            original_price=170.0,
            currency="AUD",
            is_discounted=True,
        )
        assert updated.is_discounted is True
        assert updated.current_price == 119.0

        # Should be the same row, not a new one
        count = db_conn.execute(
            "SELECT COUNT(*) FROM products_seen WHERE product_sku = 'IQ9773-400'"
        ).fetchone()[0]
        assert count == 1

    def test_mark_alerted(self, db_conn):
        upsert_sighting(
            conn=db_conn,
            product_sku="IQ9773-400",
            retailer_id="nike_au",
            product_url="https://nike.com/au/product/123",
            title="Ja Morant AF1 Denim",
            sku_found="IQ9773-400",
            current_price=170.0,
            original_price=170.0,
            currency="AUD",
            is_discounted=False,
            alerted=True,
        )
        sighting = get_sighting(db_conn, "IQ9773-400", "nike_au", "https://nike.com/au/product/123")
        assert sighting is not None
        assert sighting.last_alerted_at is not None


class TestScrapeLog:
    def test_record_successful_scrape(self, db_conn):
        record_scrape(
            conn=db_conn,
            retailer_id="nike_au",
            url="https://nike.com/au/w?q=test",
            success=True,
            products_found=2,
        )
        rows = db_conn.execute("SELECT * FROM scrape_log").fetchall()
        assert len(rows) == 1
        assert rows[0]["success"] == 1
        assert rows[0]["products_found"] == 2

    def test_record_failed_scrape(self, db_conn):
        record_scrape(
            conn=db_conn,
            retailer_id="nike_au",
            url="https://nike.com/au/w?q=test",
            success=False,
            error_type="timeout",
            error_message="Connection timed out",
        )
        health = get_retailer_health(db_conn)
        assert len(health) == 1
        assert health[0]["consecutive_failures"] == 1
        assert health[0]["last_error_type"] == "timeout"

    def test_consecutive_failures_reset_on_success(self, db_conn):
        record_scrape(db_conn, "nike_au", "url1", success=False, error_type="timeout")
        record_scrape(db_conn, "nike_au", "url1", success=False, error_type="dns")
        record_scrape(db_conn, "nike_au", "url1", success=True, products_found=1)

        health = get_retailer_health(db_conn)
        assert health[0]["consecutive_failures"] == 0
        assert health[0]["last_success_at"] is not None
