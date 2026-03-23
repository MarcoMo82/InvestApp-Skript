"""Tests für den LevelAgent."""
import numpy as np
import pandas as pd
import pytest

from agents.level_agent import LevelAgent


class TestLevelAgent:
    def test_output_keys_present(self, sample_ohlcv):
        agent = LevelAgent()
        current_price = float(sample_ohlcv["close"].iloc[-1])
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv": sample_ohlcv, "current_price": current_price}
        )
        for key in ("key_levels", "nearest_level", "distance_pct", "reaction_score",
                    "daily_high", "daily_low"):
            assert key in result, f"Schlüssel '{key}' fehlt im Output"

    def test_daily_high_low_correct(self, sample_ohlcv):
        agent = LevelAgent()
        current_price = float(sample_ohlcv["close"].iloc[-1])
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv": sample_ohlcv, "current_price": current_price}
        )
        expected_high = float(sample_ohlcv["high"].iloc[-96:].max())
        expected_low = float(sample_ohlcv["low"].iloc[-96:].min())
        assert result["daily_high"] == pytest.approx(expected_high, rel=1e-5)
        assert result["daily_low"] == pytest.approx(expected_low, rel=1e-5)

    def test_nearest_level_returned(self, sample_ohlcv):
        agent = LevelAgent()
        current_price = float(sample_ohlcv["close"].iloc[-1])
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv": sample_ohlcv, "current_price": current_price}
        )
        assert result["nearest_level"] is not None
        assert "price" in result["nearest_level"]
        assert "type" in result["nearest_level"]

    def test_key_levels_not_empty(self, sample_ohlcv):
        agent = LevelAgent()
        current_price = float(sample_ohlcv["close"].iloc[-1])
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv": sample_ohlcv, "current_price": current_price}
        )
        assert len(result["key_levels"]) > 0

    def test_reaction_score_in_range(self, sample_ohlcv):
        agent = LevelAgent()
        current_price = float(sample_ohlcv["close"].iloc[-1])
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv": sample_ohlcv, "current_price": current_price}
        )
        assert 1 <= result["reaction_score"] <= 10

    def test_distance_pct_non_negative(self, sample_ohlcv):
        agent = LevelAgent()
        current_price = float(sample_ohlcv["close"].iloc[-1])
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv": sample_ohlcv, "current_price": current_price}
        )
        assert result["distance_pct"] >= 0

    def test_insufficient_data_returns_default(self):
        agent = LevelAgent()
        tiny_df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.0] * 5,
                "volume": [1000] * 5,
            }
        )
        result = agent.analyze({"symbol": "AAPL", "ohlcv": tiny_df, "current_price": 100.0})
        # Unzureichende Daten → Fallback-Result
        assert "key_levels" in result

    def test_current_price_defaults_to_last_close(self, sample_ohlcv):
        """Wenn current_price nicht übergeben wird, nutzt Agent den letzten Close."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert "nearest_level" in result
