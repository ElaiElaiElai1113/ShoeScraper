import pytest

from sneakers.config import load_config


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
