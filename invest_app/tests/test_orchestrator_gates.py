"""Integrationstests für Orchestrator-Gates (Macro, Volatility, Entry)."""
import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np


def _make_ohlcv(n=100):
    np.random.seed(42)
    prices = [100.0]
    for _ in range(1, n):
        prices.append(max(prices[-1] + np.random.normal(0.05, 0.5), 1.0))
    df = pd.DataFrame(
        {
            "open": [p * 0.999 for p in prices],
            "high": [p * 1.005 for p in prices],
            "low": [p * 0.995 for p in prices],
            "close": prices,
            "volume": np.ones(n) * 1000,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="15min"),
    )
    return df


class TestOrchestratorGates:
    def test_macro_gate_blocks_on_high_event_risk(self):
        """Kalender liefert High-Impact Event → event_risk=high, trading_allowed=False."""
        from datetime import datetime, timedelta, timezone

        mock_client = MagicMock()
        mock_client.analyze.return_value = (
            '{"macro_bias": "neutral", "event_risk": "high",'
            ' "trading_allowed": false, "key_themes": ["FOMC"],'
            ' "reasoning": "Hohe Event-Gefahr"}'
        )
        mock_fetcher = MagicMock()
        mock_fetcher.get_yahoo_news.return_value = []
        mock_fetcher.get_economic_calendar_summary.return_value = "FOMC heute"

        # Kalender-Mock: liefert High-Impact Event in 1h
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        mock_cal_instance = MagicMock()
        mock_cal_instance.get_events.return_value = [{
            "time": future_time,
            "currency": "USD",
            "name": "FOMC Statement",
            "impact": "high",
        }]
        mock_cal_instance.last_source = "JBlanked"

        from agents.macro_agent import MacroAgent
        with patch("agents.macro_agent.EconomicCalendar", return_value=mock_cal_instance):
            agent = MacroAgent(claude_client=mock_client, news_fetcher=mock_fetcher)
            result = agent.analyze({"symbol": "EURUSD"})

        assert result["trading_allowed"] is False
        assert result["event_risk"] == "high"
        assert result["calendar_source"] == "JBlanked"

    def test_macro_gate_allows_low_risk(self):
        """MacroAgent mit event_risk=low → trading_allowed=True."""
        mock_client = MagicMock()
        mock_client.analyze.return_value = (
            '{"macro_bias": "bullish", "event_risk": "low",'
            ' "trading_allowed": true, "key_themes": ["Fed pause"],'
            ' "reasoning": "Stabile Makrolage"}'
        )
        mock_fetcher = MagicMock()
        mock_fetcher.get_yahoo_news.return_value = []
        mock_fetcher.get_economic_calendar_summary.return_value = ""

        from agents.macro_agent import MacroAgent
        agent = MacroAgent(claude_client=mock_client, news_fetcher=mock_fetcher)
        result = agent.analyze({"symbol": "EURUSD"})
        assert result["trading_allowed"] is True

    def test_volatility_gate_blocks_low_atr(self):
        """Sehr niedrige ATR → setup_allowed=False."""
        from agents.volatility_agent import VolatilityAgent

        n = 100
        df = pd.DataFrame(
            {
                "open": np.ones(n) * 100.0,
                "high": np.ones(n) * 100.001,
                "low": np.ones(n) * 99.999,
                "close": np.ones(n) * 100.0,
                "volume": np.ones(n) * 1000,
            }
        )
        agent = VolatilityAgent(min_atr_pct=0.005)  # hohe Mindest-ATR
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": df})
        assert result["setup_allowed"] is False

    def test_risk_gate_enforces_crv(self):
        """RiskAgent erzwingt Mindest-CRV."""
        from agents.risk_agent import RiskAgent
        agent = RiskAgent(min_crv=2.0)
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=1.0, account_balance=10000
        )
        if result["trade_allowed"]:
            assert result["crv"] >= 2.0

    def test_signal_model_validation(self):
        """Signal.is_valid() prüft alle Mindestanforderungen korrekt."""
        from models.signal import Signal, Direction, SignalStatus

        valid = Signal(
            instrument="EURUSD",
            direction=Direction.LONG,
            entry_price=1.08,
            stop_loss=1.076,
            take_profit=1.088,
            crv=2.0,
            confidence_score=85.0,
            status=SignalStatus.APPROVED,
        )
        assert valid.is_valid() is True

        invalid_low_conf = Signal(
            instrument="EURUSD",
            direction=Direction.LONG,
            entry_price=1.08,
            stop_loss=1.076,
            take_profit=1.088,
            crv=2.0,
            confidence_score=70.0,  # unter 80%
            status=SignalStatus.REJECTED,
        )
        assert invalid_low_conf.is_valid() is False

        invalid_neutral = Signal(
            instrument="EURUSD",
            direction=Direction.NEUTRAL,
            entry_price=1.08,
            stop_loss=1.076,
            take_profit=1.088,
            crv=2.0,
            confidence_score=85.0,
        )
        assert invalid_neutral.is_valid() is False

    def test_pipeline_sequential_dependency(self):
        """Wenn Trend neutral ist → long_allowed=False und short_allowed=False."""
        from agents.trend_agent import TrendAgent

        small_df = pd.DataFrame(
            {
                "open": [100.0] * 5,
                "high": [101.0] * 5,
                "low": [99.0] * 5,
                "close": [100.0] * 5,
                "volume": [1000] * 5,
            }
        )
        agent = TrendAgent()
        result = agent.analyze({"symbol": "EURUSD", "ohlcv": small_df})
        assert result["direction"] == "neutral"
        assert result["long_allowed"] is False
        assert result["short_allowed"] is False
