from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from sneakers.models import RawProduct


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_price_values(text: str) -> list[float]:
    prices: list[float] = []
    seen = set()
    for match in re.finditer(r"(?:aud\s*|au\s*\$|\$)\s*(\d[\d,]*(?:\.\d{2})?)", text.lower()):
        try:
            price = round(float(match.group(1).replace(",", "")), 2)
        except ValueError:
            continue
        if price not in seen:
            seen.add(price)
            prices.append(price)
    return prices


def infer_availability(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("sold out", "out of stock", "unavailable", "notify me", "coming soon")):
        return "unavailable"
    if any(term in lowered for term in ("add to bag", "add to cart", "in stock", "available", "select size")):
        return "available"
    return "possible"


def extract_candidates_from_html(base_url: str, html: str, retailer_id: str, source_type: str = "retail") -> list[RawProduct]:
    soup = BeautifulSoup(html or "", "html.parser")
    products: list[RawProduct] = []
    for link in soup.find_all("a", href=True):
        title = normalize_whitespace(link.get_text(" ", strip=True))
        if not title:
            continue
        container = link.find_parent(["article", "li", "div"]) or link.parent
        blob = normalize_whitespace(container.get_text(" ", strip=True) if container else title)
        prices = extract_price_values(blob)
        current_price = min(prices) if prices else None
        original_price = max(prices) if len(prices) > 1 and max(prices) > min(prices) else current_price
        products.append(
            RawProduct(
                retailer_id=retailer_id,
                title=title[:300],
                url=urljoin(base_url, link["href"].strip()),
                current_price=current_price,
                original_price=original_price,
                source_type=source_type,
                condition_type="retail" if source_type == "retail" else "second_hand",
                availability=infer_availability(blob),
                blob=blob[:2000],
            )
        )
    return _dedupe(products)


def extract_nike_candidates(base_url: str, html: str, retailer_id: str) -> list[RawProduct]:
    soup = BeautifulSoup(html or "", "html.parser")
    cards = soup.select('[data-testid*="product"], .product-card, .product-grid__card')
    products: list[RawProduct] = []
    for card in cards:
        link = card.find("a", href=True)
        if not link:
            continue
        title = normalize_whitespace(link.get_text(" ", strip=True) or card.get_text(" ", strip=True))
        if not title:
            continue
        blob = normalize_whitespace(card.get_text(" ", strip=True))
        prices = extract_price_values(blob)
        image = card.find("img")
        products.append(
            RawProduct(
                retailer_id=retailer_id,
                title=title[:300],
                url=urljoin(base_url, link["href"].strip()),
                current_price=min(prices) if prices else None,
                original_price=max(prices) if len(prices) > 1 and max(prices) > min(prices) else (prices[0] if prices else None),
                source_type="retail",
                condition_type="retail",
                image_url=image.get("src") if image and image.get("src") else None,
                availability=infer_availability(blob),
                blob=blob[:2000],
            )
        )
    return _dedupe(products) or extract_candidates_from_html(base_url, html, retailer_id, "retail")


def extract_ebay_candidates(base_url: str, html: str, retailer_id: str) -> list[RawProduct]:
    soup = BeautifulSoup(html or "", "html.parser")
    items = soup.select("li.s-item, .s-item")
    products: list[RawProduct] = []
    for item in items:
        link = item.select_one("a.s-item__link[href]") or item.find("a", href=True)
        if not link:
            continue
        title = normalize_whitespace(link.get_text(" ", strip=True))
        if not title or title.lower() == "shop on ebay":
            continue
        blob = normalize_whitespace(item.get_text(" ", strip=True))
        prices = extract_price_values(blob)
        image = item.find("img")
        condition_text = normalize_whitespace((item.select_one(".SECONDARY_INFO") or item).get_text(" ", strip=True))
        products.append(
            RawProduct(
                retailer_id=retailer_id,
                title=title[:300],
                url=urljoin(base_url, link["href"].strip()),
                current_price=min(prices) if prices else None,
                original_price=max(prices) if len(prices) > 1 and max(prices) > min(prices) else (prices[0] if prices else None),
                source_type="second_hand",
                condition_type=_condition_type(condition_text),
                image_url=image.get("src") if image and image.get("src") else None,
                location=_find_location(blob),
                availability="available",
                blob=blob[:2000],
            )
        )
    return _dedupe(products) or extract_marketplace_candidates(base_url, html, retailer_id)


def extract_marketplace_candidates(base_url: str, html: str, retailer_id: str) -> list[RawProduct]:
    products = extract_candidates_from_html(base_url, html, retailer_id, source_type="second_hand")
    soup = BeautifulSoup(html or "", "html.parser")
    by_url = {product.url: product for product in products}
    for link in soup.find_all("a", href=True):
        url = urljoin(base_url, link["href"].strip())
        product = by_url.get(url)
        if product is None:
            continue
        container = link.find_parent(["article", "li", "div"]) or link.parent
        image = container.find("img") if container else None
        location = _find_location(container.get_text(" ", strip=True) if container else "")
        by_url[url] = RawProduct(
            **{
                **product.__dict__,
                "image_url": image.get("src") if image and image.get("src") else None,
                "location": location,
                "condition_type": "second_hand",
                "source_type": "second_hand",
            }
        )
    return list(by_url.values())


def page_requires_login(html: str) -> bool:
    lowered = normalize_whitespace(html).lower()
    return any(
        marker in lowered
        for marker in (
            "log in to facebook",
            "login to facebook",
            "you must log in",
            "sign in to continue",
            "log in to continue",
        )
    )


def _find_location(text: str) -> str | None:
    cleaned = normalize_whitespace(text)
    cleaned = re.sub(r"\bfrom\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:pre-owned|used|new)\s+", "", cleaned, flags=re.IGNORECASE)
    match = re.search(r"\b[A-Z][A-Za-z .'-]+,\s*(?:NSW|VIC|QLD|WA|SA|TAS|ACT|NT)\b", cleaned)
    return match.group(0) if match else None


def _condition_type(text: str) -> str:
    lowered = text.lower()
    if "pre-owned" in lowered or "used" in lowered:
        return "pre_owned"
    if "new" in lowered:
        return "new"
    return "second_hand"


def _dedupe(products: Iterable[RawProduct]) -> list[RawProduct]:
    seen = set()
    out: list[RawProduct] = []
    for product in products:
        key = (product.title, product.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(product)
    return out
