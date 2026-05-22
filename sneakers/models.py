from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class RawProduct:
    """Output of a retailer parser — one product found on a page."""

    retailer_id: str  # e.g. "nike_au", "footlocker_au"
    title: str
    url: str
    sku: Optional[str] = None
    current_price: Optional[float] = None
    original_price: Optional[float] = None
    currency: str = "AUD"
    in_stock: Optional[bool] = None
    source_type: str = "retail"
    condition_type: str = "retail"
    image_url: Optional[str] = None
    location: Optional[str] = None
    availability: str = "possible"
    blob: str = ""

    @property
    def is_discounted(self) -> bool:
        if self.current_price is None or self.original_price is None:
            return False
        return self.current_price < self.original_price

    @property
    def discount_pct(self) -> Optional[float]:
        if not self.is_discounted:
            return None
        return round((1 - self.current_price / self.original_price) * 100, 1)


@dataclass
class ScrapeResult:
    """Outcome of scraping one retailer URL."""

    retailer_id: str
    url: str
    products: list[RawProduct] = field(default_factory=list)
    success: bool = True
    error_type: Optional[str] = None  # "timeout", "dns", "http_403", "parse_error"
    error_message: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ProductConfig:
    """One product entry from products.yaml."""

    label: str  # human-readable, e.g. "Ja Morant AF1 Denim"
    sku: str
    keywords: list[str]
    retailers: list[str]  # retailer_id values to monitor
    alert_rule: str  # "any_stock", "discount_only", "below_price", "first_markdown", "price_dropped"
    alert_threshold: Optional[float] = None  # for below_price rule
    min_discount_pct: Optional[float] = None  # for min_discount_pct rule
    required_sizes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceConfig:
    """One configured scrape/search source."""

    id: str
    name: str
    source_type: str
    search_url: str
    render_mode: str = "auto"
    parser: str = "generic"


@dataclass
class Sighting:
    """Row in the products_seen table."""

    id: Optional[int]
    product_sku: str
    retailer_id: str
    product_url: str
    title: str
    current_price: Optional[float]
    original_price: Optional[float]
    currency: str
    is_discounted: bool
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    last_alerted_at: Optional[datetime] = None
    sku_found: Optional[str] = None
    source_type: str = "retail"
    condition_type: str = "retail"
    image_url: Optional[str] = None
    location: Optional[str] = None
    availability: str = "possible"
    match_score: int = 0
    match_confidence: str = "low"
    matched_terms: list[str] = field(default_factory=list)
