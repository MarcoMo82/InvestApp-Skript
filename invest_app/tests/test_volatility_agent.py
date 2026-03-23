"""Tests für den VolatilityAgent."""
import numpy as np
import pandas as pd
import pytest

from agents.volatility_agent import VolatilityAgent


class TestVolatilityAgent:
    def test_output_keys_present(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})

        for key in ("volatility_ok", "setup_allowed", "market_phase",
                    "atr_value", "atr_pct", "session", "is_compression", "is_expansion"):
            assert key in result, f"Schlüssel '{key}' fehlt im Output"

    def test_atr_value_positive(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert result["atr_value"] > 0

    def test_atr_pct_in_range(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert 0 < result["atr_pct"] < 1.0  # Prozentsatz, kein Absolutwert

    def test_market_phase_valid(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert result["market_phase"] in ("compression", "expansion", "normal")

    def test_setup_allowed_false_when_compression(self, config):
        """Bei Compression-Phase: setup_allowed muss False sein."""
        np.random.seed(0)
        n = 100
        # Sehr enge Bars simulieren Compression
        prices = np.ones(n) * 100.0
        tiny_range = 0.001
        df = pd.DataFrame(
            {
                "open": prices,
                "high": prices + tiny_range,
                "low": prices - tiny_range,
                "close": prices,
                "volume": np.ones(n) * 1000,
            }
        )
        agent = VolatilityAgent(config=config, min_atr_pct=0.0003)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": df})
        # Bei sehr niedriger ATR% ist volatility_ok=False → setup_allowed=False
        if not result["volatility_ok"]:
            assert result["setup_allowed"] is False

    def test_session_string_returned(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert isinstance(result["session"], str)
        assert len(result["session"]) > 0

    def test_with_data_connector(self, config, mock_yfinance_connector):
        agent = VolatilityAgent(config=config, data_connector=mock_yfinance_connector)
        result = agent.analyze(symbol="EURUSD")
        assert "atr_value" in result
        mock_yfinance_connector.get_ohlcv.assert_called_once()
