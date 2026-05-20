from __future__ import annotations

from base64 import b64decode
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

from sneakers.config import AppConfig, load_config
from sneakers.db import init_db
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
}


def json_response(handler: SimpleHTTPRequestHandler, payload: Any, status: int = 200) -> None:
    body = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def products_payload(config: AppConfig) -> list[dict[str, Any]]:
    return [
        {
            "name": product.label,
            "sku": product.sku,
            "search_text": " ".join([product.label, product.sku]),
            "discount_only": product.alert_rule == "discount_only",
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


def recent_sightings_payload(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, retailer_id AS retailer, product_url AS url, title,
               '' AS matched_text, first_seen_at, last_seen_at,
               source_type, condition_type, image_url, location, availability,
               current_price, original_price
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
                   NULL AS original_price
            FROM sightings
            ORDER BY first_seen_at DESC, id DESC
            LIMIT ?
            """,
            (remaining,),
        ).fetchall()
        items.extend(dict(row) for row in legacy_rows)

    return items[:limit]


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


def run_scan_in_background() -> None:
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
            json_response(self, payload)
            return

        if path == "/api/sightings":
            json_response(self, {"sightings": get_recent_sightings()})
            return

        if path == "/api/products":
            json_response(self, {"products": products_payload(APP_CONFIG)})
            return

        if path == "/api/retailers":
            json_response(self, {"retailers": retailers_payload(APP_CONFIG)})
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
        if not self.require_authorization():
            return

        path = urlparse(self.path).path
        if path != "/api/scan":
            json_response(self, {"error": "Not found"}, status=404)
            return

        with scan_lock:
            if scan_state["running"]:
                json_response(self, {"error": "A scan is already running."}, status=409)
                return

        thread = threading.Thread(target=run_scan_in_background, daemon=True)
        thread.start()
        json_response(self, {"started": True})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ShoeScraperHandler)
    url = f"http://{HOST}:{PORT}"
    print(f"ShoeScraper frontend running at {url}")
    if should_open_browser():
        webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
