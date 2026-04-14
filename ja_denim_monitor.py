#!/usr/bin/env python3
"""
Ja Morant Air Force 1 Denim monitor
Tracks public AU retailer search/result pages for IQ9773-400 / related keywords.

Usage:
    python ja_denim_monitor.py

Optional env vars:
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
"""

from __future__ import annotations

import os
import re
import time
import sqlite3
import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# ----------------------------
# Config
# ----------------------------

DISCOUNT_TERMS = [
    "sale",
    "discount",
    "markdown",
    "reduced",
    "clearance",
    "below retail",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_REQUESTS = 3
DB_PATH = "sneaker_monitor.db"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-AU,en;q=0.9,en-US;q=0.8",
})

# ----------------------------
# Retailer targets
# ----------------------------

@dataclass
class Retailer:
    name: str
    url: str
    product: "ProductTarget"
    mode: str = "html"  # html | text_only


@dataclass(frozen=True)
class ProductTarget:
    name: str
    sku: str
    search_text: str
    target_terms: List[str]
    discount_only: bool = False
    discount_terms: List[str] = field(default_factory=lambda: DISCOUNT_TERMS.copy())


PRODUCT_TARGETS = [
    ProductTarget(
        name="Ja Morant Air Force 1 Denim",
        sku="IQ9773-400",
        search_text="Ja Morant Air Force 1 Denim",
        target_terms=[
            "iq9773-400",
            "ja morant",
            "air force 1",
            "denim",
        ],
    ),
    ProductTarget(
        name="Nike Dunk Low IR0609-100",
        sku="IR0609-100",
        search_text="Nike Dunk Low IR0609-100",
        target_terms=[
            "ir0609-100",
            "nike dunk low",
            "dunk low",
        ],
        discount_only=True,
    ),
]

def build_targets() -> List[Retailer]:
    """
    These are public search/result pages.
    Some sites may change their HTML over time.
    """
    retailers: List[Retailer] = []

    for product in PRODUCT_TARGETS:
        sku_q = quote(product.sku)
        text_q = quote(product.search_text)
        retailers.extend([
            Retailer(
                name="Nike AU SKU Search",
                url=f"https://www.nike.com/au/w?q={sku_q}",
                product=product,
            ),
            Retailer(
                name="Nike AU Text Search",
                url=f"https://www.nike.com/au/w?q={text_q}",
                product=product,
            ),
            Retailer(
                name="Foot Locker AU SKU Search",
                url=f"https://www.footlocker.com.au/en/search?query={sku_q}",
                product=product,
            ),
            Retailer(
                name="Foot Locker AU Text Search",
                url=f"https://www.footlocker.com.au/en/search?query={text_q}",
                product=product,
            ),
            Retailer(
                name="Subtype Search",
                url=f"https://subtypestore.com/search?q={sku_q}",
                product=product,
            ),
            Retailer(
                name="Up There Search",
                url=f"https://uptherestore.com/search?q={sku_q}",
                product=product,
            ),
            Retailer(
                name="Culture Kings Search",
                url=f"https://www.culturekings.com.au/search?q={sku_q}",
                product=product,
            ),
        ])

    return retailers


# ----------------------------
# DB
# ----------------------------

def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retailer TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            matched_text TEXT NOT NULL,
            first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(retailer, url, title)
        )
    """)
    conn.commit()

def already_seen(conn: sqlite3.Connection, retailer: str, url: str, title: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sightings WHERE retailer = ? AND url = ? AND title = ? LIMIT 1",
        (retailer, url, title),
    ).fetchone()
    return row is not None

def save_sighting(
    conn: sqlite3.Connection,
    retailer: str,
    url: str,
    title: str,
    matched_text: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO sightings (retailer, url, title, matched_text)
        VALUES (?, ?, ?, ?)
        """,
        (retailer, url, title, matched_text),
    )
    conn.commit()


# ----------------------------
# Telegram
# ----------------------------

def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.info("Telegram not configured; skipping alert.")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }
    try:
        r = session.post(api_url, data=payload, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as exc:
        logging.warning("Telegram send failed: %s", exc)


# ----------------------------
# Scraping helpers
# ----------------------------

def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_price_values(text: str) -> List[float]:
    prices: List[float] = []
    seen = set()

    for match in re.finditer(r"(?:aud\s*|\$)\s*(\d[\d,]*(?:\.\d{2})?)", text.lower()):
        raw_value = match.group(1).replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:
            continue

        rounded = round(value, 2)
        if rounded in seen:
            continue
        seen.add(rounded)
        prices.append(rounded)

    return prices


def looks_discounted(text: str, discount_terms: List[str]) -> bool:
    lowered = text.lower()
    prices = extract_price_values(lowered)

    if re.search(r"\b(?:sale|discount|markdown|reduced)\b", lowered):
        return True
    if re.search(r"\bclearance\b", lowered):
        return True
    if re.search(r"\bwas\b.{0,30}\bnow\b", lowered):
        return True
    if re.search(r"\b\d{1,3}%\s*off\b", lowered):
        return True
    if len(prices) >= 2 and min(prices) < max(prices):
        return True
    return any(term in lowered for term in discount_terms)

def get_html(url: str) -> Optional[str]:
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.RequestException as exc:
        logging.warning("Request failed for %s: %s", url, exc)
        return None

def extract_candidates_from_html(base_url: str, html: str) -> List[dict]:
    """
    Generic extraction:
    - links
    - card-ish containers
    - title text
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[dict] = []

    # 1) link-based extraction from product-card-like containers
    for a in soup.find_all("a", href=True):
        text = normalize_whitespace(a.get_text(" ", strip=True))
        href = a["href"].strip()
        if not text:
            continue

        container = a.find_parent(["article", "li", "div"]) or a.parent
        context_source = container.get_text(" ", strip=True) if container else text
        context_text = normalize_whitespace(context_source)

        full_url = href
        if href.startswith("/"):
            # basic absolute resolution
            from urllib.parse import urljoin
            full_url = urljoin(base_url, href)

        candidates.append({
            "title": text[:300],
            "url": full_url,
            "blob": (context_text or text)[:500],
            "prices": extract_price_values(context_text),
        })

    return dedupe_candidates(candidates)

def dedupe_candidates(items: Iterable[dict]) -> List[dict]:
    seen = set()
    out = []
    for item in items:
        key = (item["title"], item["url"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

def match_target(product: ProductTarget, blob: str) -> bool:
    text = blob.lower()
    # Strong hit: explicit SKU
    if product.sku.lower() in text:
        return not product.discount_only or looks_discounted(text, product.discount_terms)

    # Flexible hit: at least 3 target terms
    hits = sum(1 for term in product.target_terms if term in text)
    if hits < min(3, len(product.target_terms)):
        return False

    if product.discount_only:
        return looks_discounted(text, product.discount_terms)

    return True


# ----------------------------
# Main scan logic
# ----------------------------

def scan_retailer(conn: sqlite3.Connection, retailer: Retailer) -> List[dict]:
    logging.info("Checking %s for %s", retailer.name, retailer.product.sku)
    html = get_html(retailer.url)
    if not html:
        return []

    candidates = extract_candidates_from_html(retailer.url, html)
    new_hits: List[dict] = []

    for c in candidates:
        if not match_target(retailer.product, c["blob"]):
            continue

        title = normalize_whitespace(c["title"]) or "Untitled Match"
        url = c["url"]
        retailer_key = f"{retailer.name} [{retailer.product.sku}]"
        if already_seen(conn, retailer_key, url, title):
            continue

        save_sighting(conn, retailer_key, url, title, c["blob"][:1000])

        hit = {
            "retailer": retailer.name,
            "product": retailer.product.name,
            "sku": retailer.product.sku,
            "discount_only": retailer.product.discount_only,
            "title": title,
            "url": url,
            "prices": c.get("prices", []),
        }
        new_hits.append(hit)

    return new_hits


def format_alert(hit: dict) -> str:
    prices_line = ""
    if hit["prices"]:
        formatted_prices = ", ".join(f"${price:.2f}" for price in hit["prices"])
        prices_line = f"Prices seen: {formatted_prices}\n"

    return (
        "🚨 Sneaker match found\n\n"
        f"Product: {hit['product']}\n"
        f"SKU: {hit['sku']}\n"
        f"Retailer: {hit['retailer']}\n"
        f"Rule: {'discount only' if hit['discount_only'] else 'standard match'}\n"
        f"Title: {hit['title']}\n"
        f"{prices_line}"
        f"Link: {hit['url']}"
    )

def run_once() -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    all_hits: List[dict] = []
    for retailer in build_targets():
        hits = scan_retailer(conn, retailer)
        all_hits.extend(hits)
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    if not all_hits:
        logging.info("No new matches found.")
        return

    logging.info("Found %d new matches.", len(all_hits))
    for hit in all_hits:
        alert = format_alert(hit)
        print(alert)
        send_telegram(alert)


if __name__ == "__main__":
    run_once()
