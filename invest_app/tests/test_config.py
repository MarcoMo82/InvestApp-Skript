"""Tests für die Config-Klasse."""
import os
import pytest


class TestConfig:
    def test_config_loads_env_defaults(self, config):
        assert config.trading_mode == "demo"
        assert config.risk_per_trade == pytest.approx(0.01)
        assert config.max_daily_loss == pytest.approx(0.03)

    def test_config_api_key_is_string(self, config):
        # API-Key muss ein String sein (leer im Test-Env ohne echtes .env)
        assert isinstance(config.anthropic_api_key, str)

    def test_config_fixed_defaults(self, config):
        assert config.min_confidence_score == pytest.approx(80.0)
        assert config.min_crv == pytest.approx(2.0)
        assert config.atr_period == 14
        assert config.atr_sl_multiplier == pytest.approx(2.0)
        assert config.atr_tp_multiplier == pytest.approx(4.0)

    def test_config_symbols(self, config):
        assert "EURUSD" in config.forex_symbols
        assert "AAPL" in config.stock_symbols
        assert "BTCUSD" in config.crypto_symbols

    def test_config_all_symbols(self, config):
        all_syms = config.all_symbols
        assert len(all_syms) > 0
        assert "EURUSD" in all_syms
        assert "AAPL" in all_syms

    def test_config_is_not_live(self, config):
        assert config.is_live is False

    def test_config_ema_periods(self, config):
        assert config.ema_periods == [9, 21, 50, 200]

    def test_config_paths_exist(self, config):
        assert config.log_dir.exists()
        assert config.output_dir.exists()
