# Client Operations Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client product editing, Nike/eBay parser quality, match confidence, dashboard filters/export, and retry/backoff.

**Architecture:** Extend the current YAML-backed configuration, parser routing, SQLite sighting schema, service scan/search flow, and vanilla JS dashboard without replacing the app stack. Keep generic parser and manual config compatibility as fallbacks.

**Tech Stack:** Python stdlib HTTP server, SQLite, PyYAML, BeautifulSoup, vanilla HTML/CSS/JS, pytest.

---

### Task 1: Backend Data And Config

- [ ] Add tests for product save/load and confidence columns.
- [ ] Add YAML product writer that preserves sources/settings.
- [ ] Extend sightings schema with match score, confidence, and matched terms.

### Task 2: Matching, Parsers, And Retry

- [ ] Add tests for Nike/eBay parser extraction, confidence scoring, and retry attempts.
- [ ] Add parser routing for `nike` and `ebay`.
- [ ] Extend `product_matches` and service scan/search payloads with confidence metadata.
- [ ] Add configurable source retry/backoff around fetches.

### Task 3: Web APIs And Dashboard

- [ ] Add tests for products POST, sightings filters, and CSV export helpers.
- [ ] Add product admin API and filtered sightings/export payloads.
- [ ] Add dashboard controls for product editing, filters, and export links.

### Task 4: Verification

- [ ] Run focused tests for changed modules.
- [ ] Run full `pytest`.
- [ ] Run `git diff --check`.
