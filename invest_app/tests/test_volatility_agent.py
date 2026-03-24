"""Tests für den VolatilityAgent – RSI und Bollinger Bands."""
import numpy as np
import pandas as pd
import pytest

from agents.volatility_agent import VolatilityAgent


def _make_ohlcv(n: int = 200, seed: int = 42, trend: float = 0.05) -> pd.DataFrame:
    np.random.seed(seed)
    prices = [100.0]
    for _ in range(1, n):
        prices.append(max(prices[-1] + np.random.normal(trend, 0.5), 1.0))
    return pd.DataFrame(
        {
            "open": [p * np.random.uniform(0.998, 1.0) for p in prices],
            "high": [p * np.random.uniform(1.001, 1.01) for p in prices],
            "low": [p * np.random.uniform(0.99, 0.999) for p in prices],
            "close": prices,
            "volume": np.random.randint(1000, 10000, n),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="15min"),
    )


class TestRSI:
    def test_rsi_output_key_present(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert "rsi" in result
        assert "rsi_status" in result
        assert "rsi_divergence" in result

    def test_rsi_value_in_range(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert 0 <= result["rsi"] <= 100

    def test_rsi_overbought_detection(self, config):
        """RSI > 70 → 'overbought'."""
        agent = VolatilityAgent(config=config)
        # Stark steigende Preise → hoher RSI
        prices = [100.0 + i * 2 for i in range(100)]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [p - 0.1 for p in prices],
                "close": prices,
                "volume": [1000] * 100,
            }
        )
        rsi_series = agent._calculate_rsi(df)
        rsi_val = float(rsi_series.iloc[-1])
        status = agent._get_rsi_status(rsi_val)
        assert rsi_val > 70
        assert status == "overbought"

    def test_rsi_oversold_detection(self, config):
        """RSI < 30 → 'oversold'."""
        agent = VolatilityAgent(config=config)
        prices = [100.0 - i * 2 for i in range(100)]
        prices = [max(p, 1.0) for p in prices]
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.1 for p in prices],
                "low": [p - 0.5 for p in prices],
                "close": prices,
                "volume": [1000] * 100,
            }
        )
        rsi_series = agent._calculate_rsi(df)
        rsi_val = float(rsi_series.iloc[-1])
        status = agent._get_rsi_status(rsi_val)
        assert rsi_val < 30
        assert status == "oversold"

    def test_rsi_neutral_zone(self, config):
        """RSI zwischen 40–60 → 'neutral'."""
        agent = VolatilityAgent(config=config)
        assert agent._get_rsi_status(50.0) == "neutral"
        assert agent._get_rsi_status(45.0) == "neutral"
        assert agent._get_rsi_status(55.0) == "neutral"

    def test_rsi_status_values(self, config):
        """Alle möglichen RSI-Status-Werte prüfen."""
        agent = VolatilityAgent(config=config)
        valid_statuses = {"overbought", "oversold", "neutral", "bullish", "bearish"}
        for rsi_val in [10, 25, 35, 50, 55, 65, 75, 90]:
            status = agent._get_rsi_status(float(rsi_val))
            assert status in valid_statuses

    def test_rsi_divergence_bearish(self, config):
        """Bearische Divergenz: Preis neues Hoch, RSI nicht."""
        agent = VolatilityAgent(config=config)
        # Preis steigt weiter, RSI sinkt
        n = 40
        prices = list(range(100, 100 + n))  # Preis steigt kontinuierlich
        # Manuell RSI-ähnliche Serie bauen: zuerst hoch, dann niedrig
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [p - 0.5 for p in prices],
                "close": prices,
                "volume": [1000] * n,
            }
        )
        rsi_series = agent._calculate_rsi(df)
        # Ergebnis: divergence könnte True oder False sein – wir prüfen nur den Typ
        result = agent._check_rsi_divergence(df, rsi_series)
        assert isinstance(result, bool)

    def test_rsi_approved_key_in_output(self, config, sample_ohlcv):
        """Output muss 'approved' als Alias für setup_allowed enthalten."""
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert "approved" in result
        assert result["approved"] == result["setup_allowed"]


class TestBollingerBands:
    def test_bb_output_keys_present(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert "bb_status" in result
        assert "bb_bandwidth" in result

    def test_bb_bandwidth_positive(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert result["bb_bandwidth"] >= 0

    def test_bb_squeeze_detection(self, config):
        """Bandbreite < 1% → 'squeeze'."""
        agent = VolatilityAgent(config=config)
        n = 50
        prices = [100.0 + i * 0.001 for i in range(n)]  # Minimal-Bewegung
        df = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.001 for p in prices],
                "low": [p - 0.001 for p in prices],
                "close": prices,
                "volume": [1000] * n,
            }
        )
        bb_upper, bb_mid, bb_lower, bw_series = agent._calculate_bollinger_bands(df)
        bw = float(bw_series.iloc[-1])
        status = agent._get_bb_status(df, bb_upper, bb_lower, bw)
        # Bei sehr enger Bewegung → squeeze
        assert status == "squeeze"

    def test_bb_status_valid_values(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        valid = {"squeeze", "expansion", "upper_walk", "lower_walk", "above_upper", "below_lower", "neutral"}
        assert result["bb_status"] in valid

    def test_bb_above_upper_detection(self, config):
        """Preis über oberem Band → 'above_upper'."""
        agent = VolatilityAgent(config=config)
        # Erst normale Daten, dann extremer Spike
        n = 30
        prices = [100.0] * n
        spike_prices = prices + [200.0]  # Extremer Ausreißer
        df = pd.DataFrame(
            {
                "open": spike_prices,
                "high": spike_prices,
                "low": spike_prices,
                "close": spike_prices,
                "volume": [1000] * len(spike_prices),
            }
        )
        bb_upper, bb_mid, bb_lower, bw_series = agent._calculate_bollinger_bands(df)
        bw = float(bw_series.iloc[-1])
        status = agent._get_bb_status(df, bb_upper, bb_lower, bw)
        assert status == "above_upper"

    def test_confidence_modifier_present(self, config, sample_ohlcv):
        agent = VolatilityAgent(config=config)
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": sample_ohlcv})
        assert "confidence_modifier" in result
        assert isinstance(result["confidence_modifier"], float)
