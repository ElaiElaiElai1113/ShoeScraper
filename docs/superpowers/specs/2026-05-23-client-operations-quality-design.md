# Client Operations And Scrape Quality Design

## Summary
Add client-managed product configuration, Nike AU and eBay AU parser improvements, confidence scoring, dashboard filters/export, and per-source retry/backoff. This builds on the existing scheduler, health, alert, SQLite, YAML, and static dashboard structure.

## Design
The product admin API rewrites only the `products` section of `config/products.yaml` and preserves existing sources/settings. Existing basic auth remains the access control boundary.

Parser routing will support source-specific parser names for `nike` and `ebay`, with generic and marketplace parsing retained as fallback. Confidence scoring will come from `product_matches` and will be stored with sightings.

Dashboard filters will be query-string driven against existing APIs. CSV export will use the same filtered backend rows. Retry/backoff will wrap source fetches and record one health failure after all attempts fail.

## Testing
Tests cover YAML product save/load, parser fixture behavior, confidence metadata, sighting filtering/export payloads, and retry attempts before source failure.
