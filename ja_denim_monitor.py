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
from urllib.parse import quote, urlparse

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


SUPPORTED_RETAILERS = [
    {
        "id": "nike_au",
        "name": "Nike AU",
        "search_url": "https://www.nike.com/au/w?q={query}",
    },
    {
        "id": "footlocker_au",
        "name": "Foot Locker AU",
        "search_url": "https://www.footlocker.com.au/en/search?query={query}",
    },
    {
        "id": "jd_sports_au",
        "name": "JD Sports AU",
        "search_url": "https://www.jd-sports.com.au/search?q={query}",
    },
    {
        "id": "platypus",
        "name": "Platypus Shoes",
        "search_url": "https://www.platypusshoes.com.au/search?q={query}",
    },
    {
        "id": "hype_dc",
        "name": "Hype DC",
        "search_url": "https://www.hypedc.com/au/search?q={query}",
    },
    {
        "id": "the_iconic",
        "name": "THE ICONIC",
        "search_url": "https://www.theiconic.com.au/catalog/?q={query}",
    },
    {
        "id": "athletes_foot",
        "name": "The Athlete's Foot",
        "search_url": "https://www.theathletesfoot.com.au/catalogsearch/result/?q={query}",
    },
    {
        "id": "subtype",
        "name": "Subtype",
        "search_url": "https://subtypestore.com/search?q={query}",
    },
    {
        "id": "upthere",
        "name": "Up There",
        "search_url": "https://uptherestore.com/search?q={query}",
    },
    {
        "id": "culturekings",
        "name": "Culture Kings",
        "search_url": "https://www.culturekings.com.au/search?q={query}",
    },
    {
        "id": "supply_store",
        "name": "Supply Store",
        "search_url": "https://supplystore.com.au/search?q={query}",
    },
    {
        "id": "shoegrab",
        "name": "ShoeGrab",
        "search_url": "https://shoegrab.com.au/search?q={query}",
    },
]

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
    required_sizes: List[str] = field(default_factory=list)
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
    ProductTarget(
        name="Jordan 9 Retro Wheat",
        sku="AR4491-700",
        search_text="Jordan 9 Retro Wheat",
        target_terms=[
            "ar4491-700",
            "jordan 9 retro",
            "wheat",
        ],
        required_sizes=["10"],
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

        if product.required_sizes:
            retailers.append(
                Retailer(
                    name="Foot Locker AU Product Page",
                    url="https://www.footlocker.com.au/en/product/~/244101453504.html",
                    product=product,
                    mode="product_page",
                )
            )

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


def tokenize_query(query: str) -> List[str]:
    words = re.findall(r"[a-z0-9-]+", query.lower())
    return [word for word in words if len(word) > 1]


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


def infer_availability(text: str) -> str:
    lowered = text.lower()
    unavailable_patterns = [
        "sold out",
        "out of stock",
        "unavailable",
        "notify me",
        "coming soon",
    ]
    available_patterns = [
        "add to bag",
        "add to cart",
        "in stock",
        "available",
        "select size",
    ]
    if any(pattern in lowered for pattern in unavailable_patterns):
        return "unavailable"
    if any(pattern in lowered for pattern in available_patterns):
        return "available"
    return "possible"


def size_patterns(size: str) -> List[str]:
    clean = normalize_whitespace(size).lower()
    if not clean:
        return []
    escaped = re.escape(clean)
    return [
        rf"(?<!\S){escaped}(?!\S)",
        rf"\bus\s*(?:m(?:en)?|w(?:omen)?)?\s*{escaped}\b",
        rf"\b(?:m(?:en)?|w(?:omen)?)\s*{escaped}\b",
        rf"\bsize\s*{escaped}\b",
    ]


def has_size_signal(size: str, text: str) -> bool:
    if not size:
        return False
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in size_patterns(size))


def score_candidate(query_terms: List[str], candidate: dict) -> int:
    haystack = f"{candidate.get('title', '')} {candidate.get('blob', '')}".lower()
    if not query_terms:
        return 0
    return sum(1 for term in query_terms if term in haystack)


def clean_result_title(title: str) -> str:
    title = normalize_whitespace(title)
    if len(title) <= 140:
        return title
    return f"{title[:137].rstrip()}..."


def search_shoes(
    query: str,
    retailer_ids: Optional[List[str]] = None,
    deals_only: bool = False,
    size: str = "",
    max_results_per_retailer: int = 8,
) -> List[dict]:
    query = normalize_whitespace(query)
    size = normalize_whitespace(size)
    if not query:
        return []

    requested = set(retailer_ids or [])
    retailers = [
        retailer for retailer in SUPPORTED_RETAILERS
        if not requested or retailer["id"] in requested
    ]
    query_terms = tokenize_query(query)
    search_q = quote(query)
    results: List[dict] = []

    for retailer in retailers:
        search_url = retailer["search_url"].format(query=search_q)
        html = get_html(search_url)
        if not html:
            continue

        candidates = extract_candidates_from_html(search_url, html)
        retailer_results = []
        for candidate in candidates:
            score = score_candidate(query_terms, candidate)
            if score == 0:
                continue

            blob = candidate.get("blob", "")
            is_deal = looks_discounted(blob, DISCOUNT_TERMS)
            if deals_only and not is_deal:
                continue

            prices = candidate.get("prices", [])
            price = min(prices) if prices else None
            was_price = max(prices) if len(prices) >= 2 and max(prices) > min(prices) else None
            title = clean_result_title(candidate.get("title", "Untitled result"))
            size_found = has_size_signal(size, blob) if size else False
            parsed_url = urlparse(candidate.get("url", ""))
            if not parsed_url.scheme.startswith("http"):
                continue

            retailer_results.append({
                "title": title,
                "retailer": retailer["name"],
                "retailer_id": retailer["id"],
                "price": price,
                "was_price": was_price,
                "prices": prices,
                "is_deal": is_deal,
                "availability": infer_availability(blob),
                "requested_size": size,
                "size_match": "found" if size_found else "unknown",
                "url": candidate["url"],
                "matched_terms": score,
                "query_terms": len(query_terms),
                "source_search_url": search_url,
            })

        retailer_results.sort(
            key=lambda item: (
                item["is_deal"],
                item["size_match"] == "found",
                item["matched_terms"],
                item["price"] is not None,
            ),
            reverse=True,
        )
        results.extend(retailer_results[:max_results_per_retailer])

    results.sort(
        key=lambda item: (
            item["is_deal"],
            item["size_match"] == "found",
            item["matched_terms"],
            item["price"] is not None,
        ),
        reverse=True,
    )
    return results

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


def extract_product_page_candidate(base_url: str, html: str) -> List[dict]:
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find(["h1", "title"])
    title = normalize_whitespace(title_node.get_text(" ", strip=True)) if title_node else base_url
    blob = normalize_whitespace(soup.get_text(" ", strip=True))
    return [{
        "title": title[:300],
        "url": base_url,
        "blob": blob[:2000],
        "prices": extract_price_values(blob),
    }]

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


def has_required_sizes(product: ProductTarget, blob: str) -> bool:
    if not product.required_sizes:
        return True

    text = blob.lower()
    return all(
        re.search(rf"(?<!\S){re.escape(size.lower())}(?!\S)", text) is not None
        for size in product.required_sizes
    )


# ----------------------------
# Main scan logic
# ----------------------------

def scan_retailer(conn: sqlite3.Connection, retailer: Retailer) -> List[dict]:
    logging.info("Checking %s for %s", retailer.name, retailer.product.sku)
    html = get_html(retailer.url)
    if not html:
        return []

    if retailer.mode == "product_page":
        candidates = extract_product_page_candidate(retailer.url, html)
    else:
        candidates = extract_candidates_from_html(retailer.url, html)
    new_hits: List[dict] = []

    for c in candidates:
        if not match_target(retailer.product, c["blob"]):
            continue
        if not has_required_sizes(retailer.product, c["blob"]):
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
            "required_sizes": retailer.product.required_sizes,
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
    sizes_line = ""
    if hit["required_sizes"]:
        sizes_line = f"Sizes required: {', '.join(hit['required_sizes'])}\n"

    return (
        "🚨 Sneaker match found\n\n"
        f"Product: {hit['product']}\n"
        f"SKU: {hit['sku']}\n"
        f"Retailer: {hit['retailer']}\n"
        f"Rule: {'discount only' if hit['discount_only'] else 'standard match'}\n"
        f"{sizes_line}"
        f"Title: {hit['title']}\n"
        f"{prices_line}"
        f"Link: {hit['url']}"
    )

def run_once(progress_callback=None) -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    all_hits: List[dict] = []
    targets = build_targets()
    for index, retailer in enumerate(targets, start=1):
        if progress_callback:
            progress_callback({
                "current": index,
                "total": len(targets),
                "retailer": retailer.name,
                "product": retailer.product.name,
                "sku": retailer.product.sku,
            })
        hits = scan_retailer(conn, retailer)
        all_hits.extend(hits)
        if index < len(targets):
            time.sleep(SLEEP_BETWEEN_REQUESTS)

    if not all_hits:
        logging.info("No new matches found.")
        return []

    logging.info("Found %d new matches.", len(all_hits))
    for hit in all_hits:
        alert = format_alert(hit)
        print(alert)
        send_telegram(alert)
    return all_hits


if __name__ == "__main__":
    run_once()
