from __future__ import annotations

from base64 import b64decode
import csv
from datetime import datetime, timedelta
from io import StringIO
import json
import os
import sqlite3
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import compare_digest
from typing import Any
from urllib.parse import parse_qs, urlparse

from sneakers.config import AppConfig, load_config, save_products_config
from sneakers.db import get_retailer_health, init_db
from sneakers.service import build_targets, run_once, search_products


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
BASIC_AUTH_USER = os.environ.get("SHOESCRAPER_USERNAME")
BASIC_AUTH_PASSWORD = os.environ.get("SHOESCRAPER_PASSWORD")
APP_CONFIG = load_config()


def should_open_browser() -> bool:
    configured = os.environ.get("SHOESCRAPER_OPEN_BROWSER")
    if configured is not None:
        return configured.lower() not in {"0", "false", "no"}
    return HOST in {"127.0.0.1", "localhost"}

scan_lock = threading.Lock()
scan_state: dict[str, Any] = {
    "running": False,
    "last_started_at": None,
    "last_finished_at": None,
    "current": None,
    "total": 0,
    "retailer": None,
    "product": None,
    "sku": None,
    "new_hits": [],
    "error": None,
    "last_trigger_type": None,
    "scheduler_enabled": False,
    "scan_interval_minutes": None,
    "scheduler_next_run_at": None,
}


def json_response(handler: SimpleHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler: SimpleHTTPRequestHandler, body: str, content_type: str, status: int = 200) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def products_payload(config: AppConfig) -> list[dict[str, Any]]:
    return [
        {
            "name": product.label,
            "sku": product.sku,
            "search_text": " ".join([product.label, product.sku]),
            "discount_only": product.alert_rule == "discount_only",
            "alert_rule": product.alert_rule,
            "alert_threshold": product.alert_threshold,
            "min_discount_pct": product.min_discount_pct,
            "keywords": product.keywords,
            "required_sizes": product.required_sizes,
            "retailers": product.retailers,
        }
        for product in config.products
    ]


def retailers_payload(config: AppConfig) -> list[dict[str, Any]]:
    return [
        {
            "id": source.id,
            "name": source.name,
            "source_type": source.source_type,
            "render_mode": source.render_mode,
            "parser": source.parser,
        }
        for source in config.sources
    ]


def scheduler_status_payload(config: AppConfig, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "scheduler_enabled": config.settings.scheduler_enabled,
        "scan_interval_minutes": config.settings.scan_interval_minutes,
        "scheduler_next_run_at": state.get("scheduler_next_run_at"),
        "last_trigger_type": state.get("last_trigger_type"),
    }


def health_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    init_db(conn)
    return {"health": get_retailer_health(conn)}


def recent_sightings_payload(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, retailer_id AS retailer, product_url AS url, title,
               '' AS matched_text, first_seen_at, last_seen_at,
               source_type, condition_type, image_url, location, availability,
               current_price, original_price, match_score, match_confidence,
               matched_terms
        FROM products_seen
        ORDER BY last_seen_at DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    items = [dict(row) for row in rows]

    has_legacy = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sightings'"
    ).fetchone()
    if has_legacy:
        remaining = max(0, limit - len(items))
        legacy_rows = conn.execute(
            """
            SELECT id, retailer, url, title, matched_text, first_seen_at,
                   first_seen_at AS last_seen_at,
                   'retail' AS source_type,
                   'retail' AS condition_type,
                   NULL AS image_url,
                   NULL AS location,
                   'possible' AS availability,
                   NULL AS current_price,
                   NULL AS original_price,
                   0 AS match_score,
                   'low' AS match_confidence,
                   '[]' AS matched_terms
            FROM sightings
            ORDER BY first_seen_at DESC, id DESC
            LIMIT ?
            """,
            (remaining,),
        ).fetchall()
        items.extend(dict(row) for row in legacy_rows)

    for item in items:
        item["matched_terms"] = _parse_json_list(item.get("matched_terms"))
    return items[:limit]


def filtered_sightings_payload(conn: sqlite3.Connection, filters: dict[str, str], limit: int = 100) -> dict[str, Any]:
    sightings = recent_sightings_payload(conn, limit)
    filtered = []
    for item in sightings:
        if filters.get("retailer") and item.get("retailer") != filters["retailer"]:
            continue
        if filters.get("availability") and item.get("availability") != filters["availability"]:
            continue
        if filters.get("condition_type") and item.get("condition_type") != filters["condition_type"]:
            continue
        if filters.get("confidence") and item.get("match_confidence") != filters["confidence"]:
            continue
        min_price = _to_float(filters.get("min_price"))
        max_price = _to_float(filters.get("max_price"))
        price = item.get("current_price")
        if min_price is not None and (price is None or float(price) < min_price):
            continue
        if max_price is not None and (price is None or float(price) > max_price):
            continue
        filtered.append(item)
    return {"sightings": filtered}


def csv_response_text(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _parse_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def get_recent_sightings(limit: int = 50) -> list[dict[str, Any]]:
    db_path = Path(APP_CONFIG.db_path)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        return recent_sightings_payload(conn, limit)
    finally:
        conn.close()


def can_start_scheduled_scan() -> bool:
    with scan_lock:
        return not bool(scan_state["running"])


def run_scan_in_background(trigger_type: str = "manual") -> None:
    global scan_state
    with scan_lock:
        scan_state.update({
            "running": True,
            "last_started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_finished_at": None,
            "current": 0,
            "total": len(build_targets(APP_CONFIG)),
            "retailer": None,
            "product": None,
            "sku": None,
            "new_hits": [],
            "error": None,
            "last_trigger_type": trigger_type,
        })

    def progress(update: dict[str, Any]) -> None:
        with scan_lock:
            scan_state.update(update)

    try:
        hits = run_once(APP_CONFIG, progress_callback=progress)
        with scan_lock:
            scan_state["new_hits"] = hits
    except Exception as exc:
        with scan_lock:
            scan_state["error"] = str(exc)
    finally:
        with scan_lock:
            scan_state["running"] = False
            scan_state["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def scheduler_loop() -> None:
    interval = max(
        APP_CONFIG.settings.scan_interval_minutes,
        APP_CONFIG.settings.minimum_scan_interval_minutes,
    )
    next_run = datetime.now() + timedelta(minutes=interval)
    with scan_lock:
        scan_state.update({
            "scheduler_enabled": APP_CONFIG.settings.scheduler_enabled,
            "scan_interval_minutes": interval,
            "scheduler_next_run_at": next_run.strftime("%Y-%m-%d %H:%M:%S"),
        })

    while True:
        time.sleep(5)
        if datetime.now() < next_run:
            continue
        if can_start_scheduled_scan():
            thread = threading.Thread(target=run_scan_in_background, kwargs={"trigger_type": "scheduled"}, daemon=True)
            thread.start()
        next_run = datetime.now() + timedelta(minutes=interval)
        with scan_lock:
            scan_state["scheduler_next_run_at"] = next_run.strftime("%Y-%m-%d %H:%M:%S")


def start_scheduler_if_enabled() -> None:
    with scan_lock:
        scan_state.update({
            "scheduler_enabled": APP_CONFIG.settings.scheduler_enabled,
            "scan_interval_minutes": APP_CONFIG.settings.scan_interval_minutes,
        })
    if not APP_CONFIG.settings.scheduler_enabled:
        return
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()


class ShoeScraperHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def is_authorized(self) -> bool:
        if not BASIC_AUTH_USER or not BASIC_AUTH_PASSWORD:
            return True

        header = self.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "basic" or not token:
            return False

        try:
            credentials = b64decode(token).decode("utf-8")
        except Exception:
            return False

        username, separator, password = credentials.partition(":")
        return (
            bool(separator)
            and compare_digest(username, BASIC_AUTH_USER)
            and compare_digest(password, BASIC_AUTH_PASSWORD)
        )

    def require_authorization(self) -> bool:
        if self.is_authorized():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="ShoeScraper"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self) -> None:
        if not self.require_authorization():
            return

        path = urlparse(self.path).path
        if path == "/api/status":
            with scan_lock:
                payload = dict(scan_state)
            payload.update(scheduler_status_payload(APP_CONFIG, payload))
            json_response(self, payload)
            return

        if path == "/api/sightings":
            params = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}
            db_path = Path(APP_CONFIG.db_path)
            if not db_path.is_absolute():
                db_path = ROOT / db_path
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                json_response(self, filtered_sightings_payload(conn, params))
            finally:
                conn.close()
            return

        if path == "/api/sightings.csv":
            params = {key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()}
            db_path = Path(APP_CONFIG.db_path)
            if not db_path.is_absolute():
                db_path = ROOT / db_path
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                rows = filtered_sightings_payload(conn, params)["sightings"]
            finally:
                conn.close()
            text_response(self, csv_response_text(rows), "text/csv; charset=utf-8")
            return

        if path == "/api/products":
            json_response(self, {"products": products_payload(APP_CONFIG)})
            return

        if path == "/api/retailers":
            json_response(self, {"retailers": retailers_payload(APP_CONFIG)})
            return

        if path == "/api/health":
            db_path = Path(APP_CONFIG.db_path)
            if not db_path.is_absolute():
                db_path = ROOT / db_path
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                json_response(self, health_payload(conn))
            finally:
                conn.close()
            return

        if path == "/api/search":
            params = parse_qs(urlparse(self.path).query)
            query = params.get("q", [""])[0].strip()
            retailers = [
                value
                for raw in params.get("retailers", [])
                for value in raw.split(",")
                if value
            ]
            deals_only = params.get("deals_only", ["false"])[0].lower() in {"1", "true", "yes"}
            size = params.get("size", [""])[0].strip()
            source_type = params.get("source_type", ["all"])[0].strip() or "all"
            if not query:
                json_response(self, {"error": "Search query is required."}, status=400)
                return

            db_path = Path(APP_CONFIG.db_path)
            if not db_path.is_absolute():
                db_path = ROOT / db_path
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                results = search_products(
                    config=APP_CONFIG,
                    conn=conn,
                    query=query,
                    source_ids=retailers,
                    source_type=source_type,
                    deals_only=deals_only,
                    size=size,
                )
            finally:
                conn.close()
            json_response(self, {
                "query": query,
                "deals_only": deals_only,
                "size": size,
                "source_type": source_type,
                "results": results,
            })
            return

        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        global APP_CONFIG
        if not self.require_authorization():
            return

        path = urlparse(self.path).path
        if path == "/api/products":
            length = int(self.headers.get("Content-Length", "0") or "0")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                products = payload.get("products", [])
                save_products_config(ROOT / "config" / "products.yaml", products)
                APP_CONFIG = load_config()
            except Exception as exc:
                json_response(self, {"error": str(exc)}, status=400)
                return
            json_response(self, {"products": products_payload(APP_CONFIG)})
            return

        if path != "/api/scan":
            json_response(self, {"error": "Not found"}, status=404)
            return

        with scan_lock:
            if scan_state["running"]:
                json_response(self, {"error": "A scan is already running."}, status=409)
                return

        thread = threading.Thread(target=run_scan_in_background, kwargs={"trigger_type": "manual"}, daemon=True)
        thread.start()
        json_response(self, {"started": True})


def main() -> None:
    start_scheduler_if_enabled()
    server = ThreadingHTTPServer((HOST, PORT), ShoeScraperHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"ShoeScraper frontend running at {url}")
    if should_open_browser():
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
