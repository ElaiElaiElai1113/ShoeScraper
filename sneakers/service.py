from __future__ import annotations

import sqlite3
import time
from typing import Any
from urllib.parse import quote

import requests

from sneakers.config import AppConfig, load_config
from sneakers.db import init_db, record_scrape, upsert_sighting
from sneakers.fetcher import fetch_source_html
from sneakers.matcher import product_matches
from sneakers.models import ProductConfig, RawProduct, SourceConfig
from sneakers.parsers import (
    extract_candidates_from_html,
    extract_marketplace_candidates,
    page_requires_login,
)


def build_targets(config: AppConfig | None = None) -> list[tuple[ProductConfig, SourceConfig, str]]:
    config = config or load_config()
    sources = {source.id: source for source in config.sources}
    targets = []
    for product in config.products:
        for source_id in product.retailers:
            source = sources.get(source_id)
            if source is None:
                continue
            targets.append((product, source, _source_url(source, product.sku)))
    return targets


def run_once(config: AppConfig | None = None, progress_callback=None) -> list[dict[str, Any]]:
    config = config or load_config()
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    try:
        hits: list[dict[str, Any]] = []
        targets = build_targets(config)
        for index, (product, source, url) in enumerate(targets, start=1):
            if progress_callback:
                progress_callback({
                    "current": index,
                    "total": len(targets),
                    "retailer": source.name,
                    "product": product.label,
                    "sku": product.sku,
                })
            new_hits = scan_source(conn, config, product, source, url)
            hits.extend(new_hits)
            for hit in new_hits:
                send_telegram_alert(config, hit)
            time.sleep(config.settings.sleep_between_requests)
        return hits
    finally:
        conn.close()


def search_products(
    config: AppConfig,
    conn: sqlite3.Connection,
    query: str,
    source_type: str = "all",
    source_ids: list[str] | None = None,
    deals_only: bool = False,
    size: str = "",
    max_results_per_source: int = 8,
) -> list[dict[str, Any]]:
    init_db(conn)
    source_filter = set(source_ids or [])
    results: list[dict[str, Any]] = []
    for source in config.sources:
        if source_filter and source.id not in source_filter:
            continue
        if source_type != "all" and source.source_type != source_type:
            continue
        url = _source_url(source, query)
        try:
            html = fetch_source_html(source, url, config.settings)
            candidates = parse_source(source, url, html)
            record_scrape(conn, source.id, url, True, products_found=len(candidates))
        except Exception as exc:
            record_scrape(conn, source.id, url, False, error_type=type(exc).__name__, error_message=str(exc))
            continue

        ranked = []
        for candidate in candidates:
            if not is_australian_result(candidate):
                continue
            if not _query_matches(query, candidate):
                continue
            if deals_only and not candidate.is_discounted:
                continue
            if size and not _size_in_candidate(size, candidate):
                continue
            ranked.append(candidate)
        results.extend(_product_to_result(source, item, query, url) for item in ranked[:max_results_per_source])
    return results


def scan_source(
    conn: sqlite3.Connection,
    config: AppConfig,
    product: ProductConfig,
    source: SourceConfig,
    url: str,
) -> list[dict[str, Any]]:
    try:
        html = fetch_source_html(source, url, config.settings)
        if source.id == "facebook_marketplace" and page_requires_login(html):
            raise RuntimeError("Public Facebook Marketplace results require login")
        candidates = parse_source(source, url, html)
        record_scrape(conn, source.id, url, True, products_found=len(candidates))
    except Exception as exc:
        record_scrape(conn, source.id, url, False, error_type=type(exc).__name__, error_message=str(exc))
        return []

    hits: list[dict[str, Any]] = []
    for candidate in candidates:
        if not is_australian_result(candidate):
            continue
        match = product_matches(product, candidate)
        if not match.matched:
            continue
        existing = upsert_sighting(
            conn=conn,
            product_sku=product.sku,
            retailer_id=source.id,
            product_url=candidate.url,
            title=candidate.title,
            sku_found=product.sku if product.sku.lower() in f"{candidate.title} {candidate.blob}".lower() else None,
            current_price=candidate.current_price,
            original_price=candidate.original_price,
            currency=candidate.currency,
            is_discounted=candidate.is_discounted,
            source_type=candidate.source_type,
            condition_type=candidate.condition_type,
            image_url=candidate.image_url,
            location=candidate.location,
            availability=candidate.availability,
        )
        if existing and existing.first_seen_at == existing.last_seen_at:
            hits.append(_scan_hit(product, source, candidate))
    return hits


def parse_source(source: SourceConfig, url: str, html: str) -> list[RawProduct]:
    if source.parser == "marketplace":
        return extract_marketplace_candidates(url, html, source.id)
    return extract_candidates_from_html(url, html, source.id, source.source_type)


def is_australian_result(candidate: RawProduct) -> bool:
    marketplace_ids = {"ebay_au", "gumtree_au", "facebook_marketplace"}
    if candidate.source_type == "retail" and candidate.retailer_id not in marketplace_ids:
        return True

    text = f"{candidate.title} {candidate.location or ''} {candidate.blob}".lower()
    non_au_markers = (
        " united states",
        " usa",
        " los angeles",
        " california",
        " ca ",
        " new york",
        " uk",
        " united kingdom",
        " canada",
        " eur ",
        " gbp ",
        " us $",
        " usd",
    )
    if candidate.currency.upper() not in {"AUD", "AU"}:
        return False
    if any(marker in f" {text} " for marker in non_au_markers):
        return False

    au_markers = (
        " australia",
        " nsw",
        " vic",
        " qld",
        " wa",
        " sa",
        " tas",
        " act",
        " nt",
        " sydney",
        " melbourne",
        " brisbane",
        " perth",
        " adelaide",
        " canberra",
        " hobart",
        " darwin",
    )
    return True if not candidate.location else any(marker in f" {text} " for marker in au_markers)


def send_telegram_alert(config: AppConfig, hit: dict[str, Any]) -> None:
    if not config.telegram.bot_token or not config.telegram.chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{config.telegram.bot_token}/sendMessage",
        data={"chat_id": config.telegram.chat_id, "text": format_alert(hit), "disable_web_page_preview": False},
        timeout=config.settings.request_timeout,
    )


def format_alert(hit: dict[str, Any]) -> str:
    price_line = ""
    prices = hit.get("prices") or []
    if prices:
        price_line = f"Price: ${float(prices[0]):.2f}\n"
    location_line = f"Location: {hit['location']}\n" if hit.get("location") else ""
    availability_line = f"Availability: {hit.get('availability', 'possible')}\n"
    return (
        "Sneaker match found\n\n"
        f"Product: {hit['product']}\n"
        f"SKU: {hit['sku']}\n"
        f"Retailer: {hit['retailer']}\n"
        f"Source: {hit.get('source_type', 'retail')}\n"
        f"{availability_line}"
        f"{location_line}"
        f"Title: {hit['title']}\n"
        f"{price_line}"
        f"Link: {hit['url']}"
    )


def _source_url(source: SourceConfig, query: str) -> str:
    return source.search_url.format(query=quote(query))


def _query_matches(query: str, candidate: RawProduct) -> bool:
    text = f"{candidate.title} {candidate.sku or ''} {candidate.blob}".lower()
    terms = [term for term in query.lower().split() if len(term) > 1]
    if query.lower() in text:
        return True
    return bool(terms) and any(term in text for term in terms)


def _size_in_candidate(size: str, candidate: RawProduct) -> bool:
    return product_matches(
        ProductConfig("size-check", "NO-SKU", [candidate.title], [candidate.retailer_id], "any_stock", required_sizes=[size]),
        candidate,
    ).matched


def _product_to_result(source: SourceConfig, product: RawProduct, query: str, source_url: str) -> dict[str, Any]:
    return {
        "title": product.title,
        "retailer": source.name,
        "retailer_id": source.id,
        "source_type": product.source_type,
        "condition_type": product.condition_type,
        "price": product.current_price,
        "was_price": product.original_price if product.original_price != product.current_price else None,
        "prices": [p for p in (product.current_price, product.original_price) if p is not None],
        "is_deal": product.is_discounted,
        "availability": product.availability,
        "requested_size": "",
        "size_match": "unknown",
        "url": product.url,
        "image_url": product.image_url,
        "location": product.location,
        "matched_terms": 1,
        "query_terms": max(1, len(query.split())),
        "source_search_url": source_url,
    }


def _scan_hit(product: ProductConfig, source: SourceConfig, candidate: RawProduct) -> dict[str, Any]:
    return {
        "product": product.label,
        "sku": product.sku,
        "retailer": source.name,
        "retailer_id": source.id,
        "source_type": candidate.source_type,
        "condition_type": candidate.condition_type,
        "title": candidate.title,
        "url": candidate.url,
        "prices": [p for p in (candidate.current_price, candidate.original_price) if p is not None],
        "image_url": candidate.image_url,
        "location": candidate.location,
        "availability": candidate.availability,
    }
