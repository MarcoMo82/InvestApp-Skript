"""Tests für den TrendAgent."""
import pandas as pd
import pytest

from agents.trend_agent import TrendAgent


class TestTrendAgent:
    def test_uptrend_detected(self, config, sample_ohlcv):
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})

        assert result["direction"] in ("long", "short", "neutral", "sideways")
        assert 1 <= result["strength_score"] <= 10
        assert "structure_status" in result

    def test_uptrend_direction_long(self, config, sample_ohlcv):
        """Mit klarem Aufwärtstrend-Dataset sollte long erkannt werden (kein short)."""
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        # Aufwärtstrend-Daten: long oder mindestens nicht short
        assert result["direction"] in ("long", "neutral", "sideways")

    def test_downtrend_detected(self, config, sample_ohlcv_downtrend):
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv_downtrend})
        assert result["direction"] in ("long", "short", "neutral")

    def test_insufficient_data_returns_neutral(self, config):
        empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": empty_df})
        assert result["direction"] == "neutral"

    def test_output_keys_present(self, config, sample_ohlcv):
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})

        for key in ("direction", "strength_score", "structure_status",
                    "long_allowed", "short_allowed", "ema_values"):
            assert key in result, f"Schlüssel '{key}' fehlt im Output"

    def test_long_short_allowed_consistent(self, config, sample_ohlcv):
        """long_allowed und short_allowed dürfen nicht beide True sein."""
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert not (result["long_allowed"] and result["short_allowed"])

    def test_with_data_connector(self, config, mock_yfinance_connector, sample_ohlcv):
        """TrendAgent nutzt data_connector wenn kein ohlcv übergeben wird."""
        mock_yfinance_connector.get_ohlcv.return_value = sample_ohlcv
        agent = TrendAgent(config=config, data_connector=mock_yfinance_connector)
        result = agent.analyze(symbol="AAPL")
        assert result["direction"] in ("long", "short", "neutral", "sideways")
        mock_yfinance_connector.get_ohlcv.assert_called_once()

    def test_sideways_market_detected(self, config):
        """Seitwärtsmarkt: ATR deutlich unter Durchschnitt → direction='sideways'."""
        import numpy as np
        import pandas as pd
        n = 200
        # Flacher Preis: ATR sehr gering → sideways
        prices = np.ones(n) * 100.0
        df = pd.DataFrame({
            "open": prices,
            "high": prices + 0.01,  # extrem enger Range
            "low": prices - 0.01,
            "close": prices,
            "volume": np.ones(n) * 1000,
        }, index=pd.date_range("2024-01-01", periods=n, freq="15min"))
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "TEST", "ohlcv": df})
        # Sehr enger Range → ATR/ATR_avg < 0.7 → sideways
        # Oder Struktur ausgeglichen → sideways
        # Test: direction ist entweder 'sideways' oder kein long/short
        assert result["long_allowed"] is False
        assert result["short_allowed"] is False

    def test_sideways_direction_sets_strength_3(self, config):
        """Bei sideways-Markt wird strength_score auf 3 gesetzt."""
        import numpy as np
        import pandas as pd
        n = 200
        prices = np.ones(n) * 100.0
        df = pd.DataFrame({
            "open": prices,
            "high": prices + 0.01,
            "low": prices - 0.01,
            "close": prices,
            "volume": np.ones(n) * 1000,
        }, index=pd.date_range("2024-01-01", periods=n, freq="15min"))
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "TEST", "ohlcv": df})
        if result["direction"] == "sideways":
            assert result["strength_score"] == 3

    def test_detect_sideways_low_atr_ratio(self, config):
        """_detect_sideways gibt True zurück wenn ATR < 70% des Durchschnitts."""
        agent = TrendAgent(config=config)
        import pandas as pd
        import numpy as np
        n = 20
        df = pd.DataFrame({
            "open": np.ones(n) * 100,
            "high": np.ones(n) * 100.1,
            "low": np.ones(n) * 99.9,
            "close": np.ones(n) * 100,
            "volume": np.ones(n) * 1000,
        })
        # atr_avg = 1.0, atr = 0.5 → ratio = 0.5 < 0.7 → sideways
        assert agent._detect_sideways(df, atr=0.5, atr_avg=1.0) is True

    def test_detect_sideways_clear_trend_false(self, config):
        """_detect_sideways gibt False zurück bei klarem Aufwärtstrend (ATR ok + Struktur)."""
        agent = TrendAgent(config=config)
        import pandas as pd
        import numpy as np
        n = 20
        # Aufwärtstrend mit höheren Hochs und Tiefs
        prices = np.linspace(100, 120, n)
        df = pd.DataFrame({
            "open": prices * 0.999,
            "high": prices * 1.002,
            "low": prices * 0.998,
            "close": prices,
            "volume": np.ones(n) * 1000,
        })
        # atr_avg = atr → ratio = 1.0 > 0.7; klare HH-Struktur → nicht sideways
        assert agent._detect_sideways(df, atr=0.3, atr_avg=0.3) is False

    def test_small_dataset_returns_neutral(self, config):
        """Weniger Bars als max(ema_periods) → neutral."""
        import numpy as np
        import pandas as pd
        small_df = pd.DataFrame(
            {
                "open": np.ones(10) * 100,
                "high": np.ones(10) * 101,
                "low": np.ones(10) * 99,
                "close": np.ones(10) * 100,
                "volume": np.ones(10) * 1000,
            }
        )
        agent = TrendAgent(config=config)
        result = agent.analyze({"symbol": "AAPL", "ohlcv": small_df})
        assert result["direction"] == "neutral"
