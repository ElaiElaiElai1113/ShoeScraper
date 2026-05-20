from __future__ import annotations

import requests

from sneakers.config import SettingsConfig
from sneakers.models import SourceConfig
from sneakers.parsers import extract_candidates_from_html, page_requires_login


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def fetch_source_html(source: SourceConfig, url: str, settings: SettingsConfig) -> str:
    if source.render_mode == "browser":
        return fetch_browser(url, settings)

    html = fetch_static(url, settings)
    if source.render_mode == "auto" and _needs_browser(source, url, html):
        try:
            return fetch_browser(url, settings)
        except Exception:
            return html
    return html


def fetch_static(url: str, settings: SettingsConfig) -> str:
    response = requests.get(
        url,
        timeout=settings.request_timeout,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9,en-US;q=0.8"},
    )
    response.raise_for_status()
    return response.text


def fetch_browser(url: str, settings: SettingsConfig) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python -m playwright install chromium") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT, locale="en-AU")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=settings.request_timeout * 1000)
            page.wait_for_timeout(1500)
            return page.content()
        finally:
            browser.close()


def _needs_browser(source: SourceConfig, url: str, html: str) -> bool:
    if page_requires_login(html):
        return False
    if "__NEXT_DATA__" in html or "window.__" in html:
        return True
    return len(extract_candidates_from_html(url, html, source.id, source.source_type)) < 1
