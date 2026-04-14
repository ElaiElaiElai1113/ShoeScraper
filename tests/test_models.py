from sneakers.models import RawProduct, ProductConfig, Sighting, ScrapeResult


class TestRawProduct:
    def test_is_discounted_true(self):
        p = RawProduct(
            retailer_id="nike_au",
            title="Ja Morant AF1",
            url="https://nike.com/product",
            current_price=119.0,
            original_price=170.0,
        )
        assert p.is_discounted is True

    def test_is_discounted_false_same_price(self):
        p = RawProduct(
            retailer_id="nike_au",
            title="Ja Morant AF1",
            url="https://nike.com/product",
            current_price=170.0,
            original_price=170.0,
        )
        assert p.is_discounted is False

    def test_is_discounted_false_no_prices(self):
        p = RawProduct(
            retailer_id="nike_au",
            title="Ja Morant AF1",
            url="https://nike.com/product",
        )
        assert p.is_discounted is False

    def test_discount_pct(self):
        p = RawProduct(
            retailer_id="nike_au",
            title="Ja Morant AF1",
            url="https://nike.com/product",
            current_price=119.0,
            original_price=170.0,
        )
        assert p.discount_pct == 30.0

    def test_discount_pct_none_when_not_discounted(self):
        p = RawProduct(
            retailer_id="nike_au",
            title="Ja Morant AF1",
            url="https://nike.com/product",
            current_price=170.0,
            original_price=170.0,
        )
        assert p.discount_pct is None


class TestProductConfig:
    def test_defaults(self):
        cfg = ProductConfig(
            label="Test",
            sku="IQ9773-400",
            keywords=["test"],
            retailers=["nike_au"],
            alert_rule="any_stock",
        )
        assert cfg.alert_threshold is None
        assert cfg.min_discount_pct is None


class TestScrapeResult:
    def test_defaults(self):
        result = ScrapeResult(retailer_id="nike_au", url="https://nike.com")
        assert result.success is True
        assert result.products == []
        assert result.error_type is None
