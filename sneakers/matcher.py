from __future__ import annotations

import re
from dataclasses import dataclass

from sneakers.models import ProductConfig, RawProduct


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: int = 0


def product_matches(product: ProductConfig, candidate: RawProduct) -> MatchResult:
    text = f"{candidate.title} {candidate.sku or ''} {candidate.blob}".lower()
    score = 0

    if product.sku.lower() in text:
        score += 100
    else:
        hits = sum(1 for keyword in product.keywords if keyword.lower() in text)
        if hits < min(2, len(product.keywords)):
            return MatchResult(False, hits)
        score += hits * 20

    if product.required_sizes and not all(_has_size(size, text) for size in product.required_sizes):
        return MatchResult(False, score)

    if product.alert_rule == "discount_only" and not candidate.is_discounted:
        return MatchResult(False, score)

    return MatchResult(True, score)


def _has_size(size: str, text: str) -> bool:
    escaped = re.escape(str(size).lower())
    patterns = [
        rf"(?<!\S){escaped}(?!\S)",
        rf"\bus\s*{escaped}\b",
        rf"\busm\s*{escaped}\b",
        rf"\bsize\s*{escaped}\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)
