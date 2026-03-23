"""Tests für den EntryAgent."""
import numpy as np
import pandas as pd
import pytest

from agents.entry_agent import EntryAgent


def _make_ohlcv(n=50, trend="up"):
    """Hilfsfunktion: Erstellt minimales 5m-OHLCV-Dataset."""
    np.random.seed(7)
    base = 100.0
    prices = [base]
    for _ in range(1, n):
        delta = 0.05 if trend == "up" else -0.05
        prices.append(max(prices[-1] + np.random.normal(delta, 0.2), 1.0))
    df = pd.DataFrame(
        {
            "open": [p * 0.999 for p in prices],
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.995 for p in prices],
            "close": prices,
            "volume": np.ones(n) * 1000,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="5min"),
    )
    return df


class TestEntryAgent:
    def test_output_keys_present(self):
        agent = EntryAgent()
        df = _make_ohlcv()
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv_entry": df, "direction": "long"}
        )
        for key in ("entry_found", "entry_type", "entry_price",
                    "trigger_condition", "candle_pattern"):
            assert key in result, f"Schlüssel '{key}' fehlt im Output"

    def test_entry_found_is_bool(self):
        agent = EntryAgent()
        df = _make_ohlcv()
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv_entry": df, "direction": "long"}
        )
        assert isinstance(result["entry_found"], bool)

    def test_valid_entry_types(self):
        agent = EntryAgent()
        df = _make_ohlcv()
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv_entry": df, "direction": "long"}
        )
        assert result["entry_type"] in ("breakout", "rejection", "pullback", "none")

    def test_neutral_direction_no_entry(self):
        agent = EntryAgent()
        df = _make_ohlcv()
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv_entry": df, "direction": "neutral"}
        )
        assert result["entry_found"] is False

    def test_insufficient_data_no_entry(self):
        agent = EntryAgent()
        tiny_df = pd.DataFrame(
            {
                "open": [100.0] * 3,
                "high": [101.0] * 3,
                "low": [99.0] * 3,
                "close": [100.0] * 3,
                "volume": [1000] * 3,
            }
        )
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv_entry": tiny_df, "direction": "long"}
        )
        assert result["entry_found"] is False

    def test_entry_price_positive_when_found(self):
        agent = EntryAgent()
        df = _make_ohlcv()
        nearest_level = {"price": float(df["close"].iloc[-1]) * 1.001, "type": "swing_high", "strength": 7}
        result = agent.analyze(
            {
                "symbol": "AAPL",
                "ohlcv_entry": df,
                "direction": "long",
                "nearest_level": nearest_level,
                "atr_value": 0.5,
            }
        )
        if result["entry_found"]:
            assert result["entry_price"] > 0

    def test_short_direction_accepted(self):
        agent = EntryAgent()
        df = _make_ohlcv(trend="down")
        result = agent.analyze(
            {"symbol": "AAPL", "ohlcv_entry": df, "direction": "short"}
        )
        assert result["entry_type"] in ("breakout", "rejection", "pullback", "none")
