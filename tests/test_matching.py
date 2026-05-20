from sneakers.matcher import product_matches
from sneakers.models import ProductConfig, RawProduct


def make_product(**overrides):
    data = {
        "label": "Ja Morant Air Force 1 Denim",
        "sku": "IQ9773-400",
        "keywords": ["ja morant", "air force 1", "denim"],
        "retailers": ["nike_au"],
        "alert_rule": "any_stock",
    }
    data.update(overrides)
    return ProductConfig(**data)


def test_exact_sku_match_scores_highest():
    product = make_product()
    candidate = RawProduct(
        retailer_id="ebay_au",
        title="Nike Air Force IQ9773-400",
        url="https://example.test/item",
    )

    result = product_matches(product, candidate)

    assert result.matched is True
    assert result.score >= 100


def test_keyword_match_accepts_second_hand_listing():
    product = make_product()
    candidate = RawProduct(
        retailer_id="gumtree_au",
        title="Ja Morant Air Force 1 Denim size 10",
        url="https://example.test/item",
    )

    assert product_matches(product, candidate).matched is True


def test_unrelated_listing_is_rejected():
    product = make_product()
    candidate = RawProduct(
        retailer_id="ebay_au",
        title="Adidas Samba black",
        url="https://example.test/item",
    )

    assert product_matches(product, candidate).matched is False


def test_discount_only_requires_discount_signal():
    product = make_product(alert_rule="discount_only")
    full_price = RawProduct(
        retailer_id="nike_au",
        title="Ja Morant Air Force 1 Denim IQ9773-400",
        url="https://example.test/item",
        current_price=170.0,
        original_price=170.0,
    )
    sale = RawProduct(
        retailer_id="nike_au",
        title="Ja Morant Air Force 1 Denim IQ9773-400",
        url="https://example.test/item",
        current_price=120.0,
        original_price=170.0,
    )

    assert product_matches(product, full_price).matched is False
    assert product_matches(product, sale).matched is True


def test_required_size_must_be_present_when_configured():
    product = make_product(required_sizes=["10"])
    missing_size = RawProduct(
        retailer_id="footlocker_au",
        title="Ja Morant Air Force 1 Denim IQ9773-400 US9",
        url="https://example.test/item",
    )
    matching_size = RawProduct(
        retailer_id="footlocker_au",
        title="Ja Morant Air Force 1 Denim IQ9773-400 US10",
        url="https://example.test/item",
    )

    assert product_matches(product, missing_size).matched is False
    assert product_matches(product, matching_size).matched is True
