from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from sneakers.models import Sighting


SCHEMA_PRODUCTS_SEEN = """
CREATE TABLE IF NOT EXISTS products_seen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_sku     TEXT NOT NULL,
    retailer_id     TEXT NOT NULL,
    product_url     TEXT NOT NULL,
    title           TEXT NOT NULL,
    sku_found       TEXT,
    current_price   REAL,
    original_price  REAL,
    currency        TEXT NOT NULL DEFAULT 'AUD',
    is_discounted   INTEGER NOT NULL DEFAULT 0,
    source_type     TEXT NOT NULL DEFAULT 'retail',
    condition_type  TEXT NOT NULL DEFAULT 'retail',
    image_url       TEXT,
    location        TEXT,
    availability    TEXT NOT NULL DEFAULT 'possible',
    match_score     INTEGER NOT NULL DEFAULT 0,
    match_confidence TEXT NOT NULL DEFAULT 'low',
    matched_terms   TEXT NOT NULL DEFAULT '[]',
    first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_alerted_at TEXT,
    UNIQUE(product_sku, retailer_id, product_url)
);
"""

SCHEMA_SCRAPE_LOG = """
CREATE TABLE IF NOT EXISTS scrape_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    success         INTEGER NOT NULL,
    error_type      TEXT,
    error_message   TEXT,
    products_found  INTEGER NOT NULL DEFAULT 0,
    scraped_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA_RETAILER_HEALTH = """
CREATE TABLE IF NOT EXISTS retailer_health (
    retailer_id             TEXT PRIMARY KEY,
    last_success_at         TEXT,
    last_attempt_at         TEXT NOT NULL DEFAULT (datetime('now')),
    consecutive_failures    INTEGER NOT NULL DEFAULT 0,
    last_error_type         TEXT,
    last_error_message      TEXT
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    for schema in (SCHEMA_PRODUCTS_SEEN, SCHEMA_SCRAPE_LOG, SCHEMA_RETAILER_HEALTH):
        conn.execute(schema)
    _ensure_products_seen_columns(conn)
    conn.commit()


def _ensure_products_seen_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(products_seen)").fetchall()
    }
    columns = {
        "source_type": "TEXT NOT NULL DEFAULT 'retail'",
        "condition_type": "TEXT NOT NULL DEFAULT 'retail'",
        "image_url": "TEXT",
        "location": "TEXT",
        "availability": "TEXT NOT NULL DEFAULT 'possible'",
        "match_score": "INTEGER NOT NULL DEFAULT 0",
        "match_confidence": "TEXT NOT NULL DEFAULT 'low'",
        "matched_terms": "TEXT NOT NULL DEFAULT '[]'",
    }
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE products_seen ADD COLUMN {name} {definition}")


def get_sighting(
    conn: sqlite3.Connection,
    product_sku: str,
    retailer_id: str,
    product_url: str,
) -> Optional[Sighting]:
    """Load a previous sighting for deduplication and state comparison."""
    row = conn.execute(
        """
        SELECT id, product_sku, retailer_id, product_url, title,
               sku_found, current_price, original_price, currency,
               is_discounted, first_seen_at, last_seen_at, last_alerted_at,
               source_type, condition_type, image_url, location, availability,
               match_score, match_confidence, matched_terms
        FROM products_seen
        WHERE product_sku = ? AND retailer_id = ? AND product_url = ?
        """,
        (product_sku, retailer_id, product_url),
    ).fetchone()
    if row is None:
        return None
    return _row_to_sighting(row)


def upsert_sighting(
    conn: sqlite3.Connection,
    product_sku: str,
    retailer_id: str,
    product_url: str,
    title: str,
    sku_found: Optional[str],
    current_price: Optional[float],
    original_price: Optional[float],
    currency: str,
    is_discounted: bool,
    alerted: bool = False,
    source_type: str = "retail",
    condition_type: str = "retail",
    image_url: Optional[str] = None,
    location: Optional[str] = None,
    availability: str = "possible",
    match_score: int = 0,
    match_confidence: str = "low",
    matched_terms: list[str] | None = None,
) -> Sighting:
    """
    Insert or update a sighting. Returns the current state.
    Uses ON CONFLICT DO UPDATE to keep the row always reflecting latest state.
    """
    now = datetime.utcnow().isoformat()
    alert_time = now if alerted else None
    alert_fragment = f", last_alerted_at = '{now}'" if alerted else ""
    matched_terms_json = json.dumps(matched_terms or [])

    conn.execute(
        f"""
        INSERT INTO products_seen
            (product_sku, retailer_id, product_url, title, sku_found,
             current_price, original_price, currency, is_discounted,
             source_type, condition_type, image_url, location, availability,
             match_score, match_confidence, matched_terms,
             first_seen_at, last_seen_at, last_alerted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_sku, retailer_id, product_url) DO UPDATE SET
            title = excluded.title,
            sku_found = excluded.sku_found,
            current_price = excluded.current_price,
            original_price = excluded.original_price,
            currency = excluded.currency,
            is_discounted = excluded.is_discounted,
            source_type = excluded.source_type,
            condition_type = excluded.condition_type,
            image_url = excluded.image_url,
            location = excluded.location,
            availability = excluded.availability,
            match_score = excluded.match_score,
            match_confidence = excluded.match_confidence,
            matched_terms = excluded.matched_terms,
            last_seen_at = excluded.last_seen_at
            {alert_fragment}
        """,
        (
            product_sku, retailer_id, product_url, title, sku_found,
            current_price, original_price, currency, int(is_discounted),
            source_type, condition_type, image_url, location, availability,
            match_score, match_confidence, matched_terms_json,
            now, now, alert_time,
        ),
    )
    conn.commit()
    return get_sighting(conn, product_sku, retailer_id, product_url)  # type: ignore[return-value]


def mark_alerted(
    conn: sqlite3.Connection,
    product_sku: str,
    retailer_id: str,
    product_url: str,
) -> None:
    """Update last_alerted_at for a sighting."""
    now = datetime.utcnow().isoformat()
    conn.execute(
        """
        UPDATE products_seen
        SET last_alerted_at = ?
        WHERE product_sku = ? AND retailer_id = ? AND product_url = ?
        """,
        (now, product_sku, retailer_id, product_url),
    )
    conn.commit()


def record_scrape(
    conn: sqlite3.Connection,
    retailer_id: str,
    url: str,
    success: bool,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    products_found: int = 0,
) -> None:
    """Record a scrape attempt in the log and update health."""
    now = datetime.utcnow().isoformat()

    conn.execute(
        """
        INSERT INTO scrape_log (retailer_id, url, success, error_type, error_message, products_found, scraped_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (retailer_id, url, int(success), error_type, error_message, products_found, now),
    )

    # Upsert retailer_health
    if success:
        conn.execute(
            """
            INSERT INTO retailer_health (retailer_id, last_success_at, last_attempt_at, consecutive_failures)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(retailer_id) DO UPDATE SET
                last_success_at = excluded.last_success_at,
                last_attempt_at = excluded.last_attempt_at,
                consecutive_failures = 0,
                last_error_type = NULL,
                last_error_message = NULL
            """,
            (retailer_id, now, now),
        )
    else:
        conn.execute(
            """
            INSERT INTO retailer_health (retailer_id, last_attempt_at, consecutive_failures, last_error_type, last_error_message)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(retailer_id) DO UPDATE SET
                last_attempt_at = excluded.last_attempt_at,
                consecutive_failures = consecutive_failures + 1,
                last_error_type = excluded.last_error_type,
                last_error_message = excluded.last_error_message
            """,
            (retailer_id, now, error_type, error_message),
        )

    conn.commit()


def get_retailer_health(conn: sqlite3.Connection) -> list[dict]:
    """Return health status for all retailers."""
    rows = conn.execute(
        """
        SELECT retailer_id, last_success_at, last_attempt_at,
               consecutive_failures, last_error_type, last_error_message
        FROM retailer_health
        """
    ).fetchall()
    return [
        {
            "retailer_id": r[0],
            "last_success_at": r[1],
            "last_attempt_at": r[2],
            "consecutive_failures": r[3],
            "last_error_type": r[4],
            "last_error_message": r[5],
        }
        for r in rows
    ]


def _row_to_sighting(row: tuple) -> Sighting:
    return Sighting(
        id=row[0],
        product_sku=row[1],
        retailer_id=row[2],
        product_url=row[3],
        title=row[4],
        sku_found=row[5],
        current_price=row[6],
        original_price=row[7],
        currency=row[8],
        is_discounted=bool(row[9]),
        first_seen_at=_parse_dt(row[10]),
        last_seen_at=_parse_dt(row[11]),
        last_alerted_at=_parse_dt(row[12]),
        source_type=row[13],
        condition_type=row[14],
        image_url=row[15],
        location=row[16],
        availability=row[17],
        match_score=row[18] if len(row) > 18 else 0,
        match_confidence=row[19] if len(row) > 19 else "low",
        matched_terms=_parse_terms(row[20] if len(row) > 20 else None),
    )


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _parse_terms(val: Optional[str]) -> list[str]:
    if not val:
        return []
    try:
        parsed = json.loads(val)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]
