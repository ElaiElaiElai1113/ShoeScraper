from __future__ import annotations

import re
from dataclasses import dataclass
from sneakers.models import ProductConfig, RawProduct


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    score: int = 0
    matched_terms: tuple[str, ...] = ()
    confidence: str = "low"


def product_matches(product: ProductConfig, candidate: RawProduct) -> MatchResult:
    text = f"{candidate.title} {candidate.sku or ''} {candidate.blob}".lower()
    score = 0
    matched_terms: list[str] = []

    if product.sku.lower() in text:
        score += 100
        matched_terms.append(product.sku)
    else:
        matched_terms.extend(keyword for keyword in product.keywords if keyword.lower() in text)
        hits = len(matched_terms)
        if hits < min(2, len(product.keywords)):
            return MatchResult(False, hits * 20, tuple(matched_terms), _confidence(hits * 20))
        score += hits * 20

    if product.required_sizes and not all(_has_size(size, text) for size in product.required_sizes):
        return MatchResult(False, score, tuple(matched_terms), _confidence(score))
    for size in product.required_sizes:
        matched_terms.append(f"US {size}")

    if product.alert_rule == "discount_only" and not candidate.is_discounted:
        return MatchResult(False, score, tuple(matched_terms), _confidence(score))

    return MatchResult(True, score, tuple(matched_terms), _confidence(score))


def _confidence(score: int) -> str:
    if score >= 100:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def _has_size(size: str, text: str) -> bool:
    escaped = re.escape(str(size).lower())
    patterns = [
        rf"(?<!\S){escaped}(?!\S)",
        rf"\bus\s*{escaped}\b",
        rf"\busm\s*{escaped}\b",
        rf"\bsize\s*{escaped}\b",
    ]
    return any(re.search(pattern, text) for pattern in patterns)
