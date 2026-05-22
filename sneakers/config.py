from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from sneakers.models import ProductConfig, SourceConfig


@dataclass
class TelegramConfig:
    bot_token: Optional[str]
    chat_id: Optional[str]


@dataclass
class SettingsConfig:
    request_timeout: int = 20
    sleep_between_requests: float = 3.0
    jitter_range: tuple[float, float] = (0.5, 2.0)
    health_alert_threshold_days: int = 2
    scheduler_enabled: bool = False
    scan_interval_minutes: int = 60
    minimum_scan_interval_minutes: int = 15
    retry_attempts: int = 2
    retry_backoff_seconds: float = 1.0


@dataclass
class AppConfig:
    products: list[ProductConfig]
    sources: list[SourceConfig]
    telegram: TelegramConfig
    settings: SettingsConfig
    db_path: str = "sneaker_monitor.db"


def load_config(config_path: str | Path = "config/products.yaml") -> AppConfig:
    """Load product configuration from YAML and environment variables."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    products = []
    for p in raw.get("products", []):
        products.append(
            ProductConfig(
                label=p["label"],
                sku=p["sku"],
                keywords=p.get("keywords", []),
                retailers=p.get("retailers", []),
                alert_rule=p.get("alert_rule", "any_stock"),
                alert_threshold=p.get("alert_threshold"),
                min_discount_pct=p.get("min_discount_pct"),
                required_sizes=[str(size) for size in p.get("required_sizes", [])],
            )
        )

    sources = []
    for source in raw.get("sources", []):
        sources.append(
            SourceConfig(
                id=source["id"],
                name=source["name"],
                source_type=source.get("source_type", "retail"),
                search_url=source["search_url"],
                render_mode=source.get("render_mode", "auto"),
                parser=source.get("parser", "generic"),
            )
        )

    raw_settings = raw.get("settings", {})
    jitter = raw_settings.get("jitter_range", [0.5, 2.0])
    minimum_scan_interval = int(raw_settings.get("minimum_scan_interval_minutes", 15))
    scan_interval = max(int(raw_settings.get("scan_interval_minutes", 60)), minimum_scan_interval)
    settings = SettingsConfig(
        request_timeout=raw_settings.get("request_timeout", 20),
        sleep_between_requests=raw_settings.get("sleep_between_requests", 3.0),
        jitter_range=(jitter[0], jitter[1]) if isinstance(jitter, list) else (0.5, 2.0),
        health_alert_threshold_days=raw_settings.get("health_alert_threshold_days", 2),
        scheduler_enabled=bool(raw_settings.get("scheduler_enabled", False)),
        scan_interval_minutes=scan_interval,
        minimum_scan_interval_minutes=minimum_scan_interval,
        retry_attempts=raw_settings.get("retry_attempts", 2),
        retry_backoff_seconds=raw_settings.get("retry_backoff_seconds", 1.0),
    )

    return AppConfig(
        products=products,
        sources=sources,
        telegram=TelegramConfig(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        ),
        settings=settings,
        db_path=os.getenv("DB_PATH", "sneaker_monitor.db"),
    )


def save_products_config(config_path: str | Path, products: list[dict]) -> None:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    raw["products"] = [_product_to_yaml(product) for product in products]

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(raw, f, sort_keys=False, allow_unicode=False)


def _product_to_yaml(product: dict) -> dict:
    out = {
        "label": str(product.get("label") or product.get("name") or "").strip(),
        "sku": str(product.get("sku") or "").strip(),
        "keywords": [str(value).strip() for value in product.get("keywords", []) if str(value).strip()],
        "retailers": [str(value).strip() for value in product.get("retailers", []) if str(value).strip()],
        "alert_rule": str(product.get("alert_rule") or "any_stock").strip(),
    }
    required_sizes = [str(value).strip() for value in product.get("required_sizes", []) if str(value).strip()]
    if required_sizes:
        out["required_sizes"] = required_sizes
    if product.get("alert_threshold") not in (None, ""):
        out["alert_threshold"] = float(product["alert_threshold"])
    if product.get("min_discount_pct") not in (None, ""):
        out["min_discount_pct"] = float(product["min_discount_pct"])
    if not out["label"] or not out["sku"]:
        raise ValueError("Product label and sku are required")
    return out
