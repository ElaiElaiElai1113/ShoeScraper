import pytest

from sneakers.config import load_config, save_products_config


class TestLoadConfig:
    def test_loads_products(self):
        config = load_config("config/products.yaml")
        assert len(config.products) >= 2
        assert config.products[0].sku == "IQ9773-400"
        assert config.products[1].sku == "IR0609-100"

    def test_loads_settings(self):
        config = load_config("config/products.yaml")
        assert config.settings.request_timeout == 20
        assert config.settings.jitter_range == (0.5, 2.0)
        assert config.settings.scheduler_enabled is False
        assert config.settings.scan_interval_minutes == 60
        assert config.settings.minimum_scan_interval_minutes == 15

    def test_loads_scheduler_settings(self, tmp_path):
        path = tmp_path / "products.yaml"
        path.write_text(
            """
products: []
sources: []
settings:
  scheduler_enabled: true
  scan_interval_minutes: 30
  minimum_scan_interval_minutes: 10
""",
            encoding="utf-8",
        )

        config = load_config(path)

        assert config.settings.scheduler_enabled is True
        assert config.settings.scan_interval_minutes == 30
        assert config.settings.minimum_scan_interval_minutes == 10

    def test_scan_interval_respects_minimum_guardrail(self, tmp_path):
        path = tmp_path / "products.yaml"
        path.write_text(
            """
products: []
sources: []
settings:
  scan_interval_minutes: 5
  minimum_scan_interval_minutes: 15
""",
            encoding="utf-8",
        )

        config = load_config(path)

        assert config.settings.scan_interval_minutes == 15

    def test_telegram_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
        config = load_config("config/products.yaml")
        assert config.telegram.bot_token == "test-token"
        assert config.telegram.chat_id == "test-chat"

    def test_telegram_missing_is_none(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        config = load_config("config/products.yaml")
        assert config.telegram.bot_token is None
        assert config.telegram.chat_id is None

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_product_alert_rules(self):
        config = load_config("config/products.yaml")
        assert config.products[0].alert_rule == "any_stock"
        assert config.products[1].alert_rule == "discount_only"

    def test_loads_hardcoded_targets_from_yaml(self):
        config = load_config("config/products.yaml")
        skus = {product.sku for product in config.products}
        assert {"IQ9773-400", "IR0609-100", "AR4491-700"} <= skus

    def test_loads_source_definitions(self):
        config = load_config("config/products.yaml")
        sources = {source.id: source for source in config.sources}

        assert sources["nike_au"].source_type == "retail"
        assert sources["nike_au"].render_mode == "auto"
        assert sources["ebay_au"].source_type == "second_hand"
        assert sources["gumtree_au"].parser == "marketplace"
        assert sources["facebook_marketplace"].render_mode == "browser"

    def test_loads_required_sizes(self):
        config = load_config("config/products.yaml")
        jordan = next(product for product in config.products if product.sku == "AR4491-700")
        assert jordan.required_sizes == ["10"]

    def test_loads_collectible_second_hand_targets(self):
        config = load_config("config/products.yaml")
        labels = {product.label: product for product in config.products}

        expected = {
            "Sideshow Gambit",
            "Sideshow Cyclops",
            "Sideshow Nightcrawler",
            "XM Studios Nova",
            "XM Studios Batman Shogun",
            "XM Studios Deathstroke Samurai",
            "Scrooge McDuck Statue or Artwork",
        }
        assert expected <= set(labels)
        for label in expected:
            assert labels[label].retailers == ["ebay_au", "gumtree_au", "facebook_marketplace"]

    def test_second_hand_sources_are_australia_scoped(self):
        config = load_config("config/products.yaml")
        sources = {source.id: source for source in config.sources}

        assert "www.ebay.com.au" in sources["ebay_au"].search_url
        assert "LH_PrefLoc=1" in sources["ebay_au"].search_url
        assert "www.gumtree.com.au" in sources["gumtree_au"].search_url
        assert "facebook.com/marketplace/sydney" in sources["facebook_marketplace"].search_url

    def test_save_products_config_preserves_sources_and_settings(self, tmp_path):
        path = tmp_path / "products.yaml"
        path.write_text(
            """
products: []
sources:
  - id: nike_au
    name: Nike AU
    source_type: retail
    search_url: "https://www.nike.com/au/w?q={query}"
    parser: nike
settings:
  scheduler_enabled: true
  scan_interval_minutes: 30
""",
            encoding="utf-8",
        )

        save_products_config(
            path,
            [
                {
                    "label": "Nike Vomero 5",
                    "sku": "FB9149-100",
                    "keywords": ["vomero", "nike"],
                    "retailers": ["nike_au"],
                    "alert_rule": "any_stock",
                    "required_sizes": ["10"],
                }
            ],
        )
        config = load_config(path)

        assert config.products[0].label == "Nike Vomero 5"
        assert config.products[0].required_sizes == ["10"]
        assert config.sources[0].parser == "nike"
        assert config.settings.scheduler_enabled is True
