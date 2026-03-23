"""Tests für den WatchAgent – Entry-Logik für alle Entry-Typen."""
from typing import Optional

import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock

from agents.watch_agent import WatchAgent


def _make_ohlcv(n: int = 30, price: float = 1.1000) -> pd.DataFrame:
    """Einfaches OHLCV-DataFrame mit konstantem Preis."""
    return pd.DataFrame(
        {
            "open": [price] * n,
            "high": [price * 1.001] * n,
            "low": [price * 0.999] * n,
            "close": [price] * n,
            "volume": [1000] * n,
        }
    )


def _make_connector(ohlcv: Optional[pd.DataFrame] = None) -> MagicMock:
    connector = MagicMock()
    connector.get_ohlcv.return_value = ohlcv if ohlcv is not None else _make_ohlcv()
    connector.place_order.return_value = {"order_id": "test_123"}
    return connector


class TestWatchAgentInstantiation:
    def test_basic_instantiation(self):
        connector = _make_connector()
        agent = WatchAgent(connector=connector)
        assert agent.pending_count == 0

    def test_add_pending_signal(self):
        agent = WatchAgent(connector=_make_connector())
        agent.add_pending_signal({"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1})
        assert agent.pending_count == 1

    def test_multiple_pending_signals(self):
        agent = WatchAgent(connector=_make_connector())
        for i in range(3):
            agent.add_pending_signal({"instrument": f"SYM{i}", "entry_type": "market"})
        assert agent.pending_count == 3


class TestEntryConditionPullback:
    def test_pullback_triggers_when_near_ema21(self):
        """Pullback: Preis direkt am EMA21 → Entry ausgelöst."""
        n = 30
        # Alle Close-Werte gleich → EMA21 = close = current_price → Abstand = 0 < 0.05%
        ohlcv = _make_ohlcv(n=n, price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "pullback", "entry_price": 1.1000, "direction": "long"}
        assert agent._check_entry_condition(signal, ohlcv) is True

    def test_pullback_no_trigger_when_far_from_ema21(self):
        """Pullback: Preis weit vom EMA21 entfernt → kein Entry."""
        n = 30
        prices = [1.0000] * (n - 1) + [1.1100]  # letzter Kurs deutlich höher
        ohlcv = pd.DataFrame({
            "open": prices, "high": [p * 1.001 for p in prices],
            "low": [p * 0.999 for p in prices], "close": prices, "volume": [1000] * n,
        })
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "pullback", "entry_price": 1.0000, "direction": "long"}
        # EMA21 ≈ 1.0000, current_price = 1.1100 → Abstand >> 0.05%
        assert agent._check_entry_condition(signal, ohlcv) is False


class TestEntryConditionBreakout:
    def test_breakout_triggers_at_entry_level(self):
        """Breakout: Preis exakt am entry_price → Entry ausgelöst."""
        ohlcv = _make_ohlcv(price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "breakout", "entry_price": 1.1000, "direction": "long"}
        assert agent._check_entry_condition(signal, ohlcv) is True

    def test_breakout_no_trigger_far_from_level(self):
        """Breakout: Preis weit vom entry_price → kein Entry."""
        ohlcv = _make_ohlcv(price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "breakout", "entry_price": 1.2000, "direction": "long"}
        assert agent._check_entry_condition(signal, ohlcv) is False

    def test_breakout_no_entry_price_returns_false(self):
        """Breakout ohne entry_price → False."""
        ohlcv = _make_ohlcv(price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "breakout", "entry_price": None}
        assert agent._check_entry_condition(signal, ohlcv) is False


class TestEntryConditionRejection:
    def test_rejection_buy_bullish_candle(self):
        """Rejection Long: letzte Kerze bullisch (close > open) → Entry."""
        n = 30
        ohlcv = _make_ohlcv(n=n, price=1.1000)
        ohlcv.at[ohlcv.index[-1], "open"] = 1.0990
        ohlcv.at[ohlcv.index[-1], "close"] = 1.1010  # close > open
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "rejection", "direction": "buy"}
        assert agent._check_entry_condition(signal, ohlcv) is True

    def test_rejection_buy_bearish_candle_no_entry(self):
        """Rejection Long: letzte Kerze bearisch → kein Entry."""
        n = 30
        ohlcv = _make_ohlcv(n=n, price=1.1000)
        ohlcv.at[ohlcv.index[-1], "open"] = 1.1010
        ohlcv.at[ohlcv.index[-1], "close"] = 1.0990  # close < open
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "rejection", "direction": "buy"}
        assert agent._check_entry_condition(signal, ohlcv) is False

    def test_rejection_sell_bearish_candle(self):
        """Rejection Short: letzte Kerze bearisch → Entry."""
        n = 30
        ohlcv = _make_ohlcv(n=n, price=1.1000)
        ohlcv.at[ohlcv.index[-1], "open"] = 1.1010
        ohlcv.at[ohlcv.index[-1], "close"] = 1.0990  # close < open
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "rejection", "direction": "sell"}
        assert agent._check_entry_condition(signal, ohlcv) is True


class TestEntryConditionMarket:
    def test_market_triggers_within_tolerance(self):
        """Market: Preis < 0.15% vom entry_price → sofort ausführen."""
        ohlcv = _make_ohlcv(price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1000}
        assert agent._check_entry_condition(signal, ohlcv) is True

    def test_market_no_trigger_outside_tolerance(self):
        """Market: Preis > 0.15% vom entry_price → kein sofortiger Entry."""
        ohlcv = _make_ohlcv(price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        # entry_price ist 1% entfernt
        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.0890}
        assert agent._check_entry_condition(signal, ohlcv) is False

    def test_market_no_entry_price_executes_immediately(self):
        """Market-Order ohne entry_price → sofort ausführen."""
        ohlcv = _make_ohlcv(price=1.1000)
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": None}
        assert agent._check_entry_condition(signal, ohlcv) is True


class TestCheckAndExecute:
    def test_executed_signal_removed_from_pending(self):
        """Nach Ausführung wird Signal aus der Pending-Liste entfernt."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        agent = WatchAgent(connector=connector)
        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal)
        executed = agent.check_and_execute()
        assert len(executed) == 1
        assert agent.pending_count == 0

    def test_unmet_signal_stays_pending(self):
        """Nicht erfüllte Bedingung → Signal bleibt in der Queue."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        agent = WatchAgent(connector=connector)
        # breakout far from current price
        signal = {"instrument": "EURUSD", "entry_type": "breakout", "entry_price": 1.5000}
        agent.add_pending_signal(signal)
        executed = agent.check_and_execute()
        assert len(executed) == 0
        assert agent.pending_count == 1

    def test_empty_ohlcv_keeps_signal_pending(self):
        """Leeres OHLCV → Signal bleibt pending, kein Absturz."""
        connector = _make_connector(pd.DataFrame())
        agent = WatchAgent(connector=connector)
        agent.add_pending_signal({"instrument": "EURUSD", "entry_type": "market"})
        executed = agent.check_and_execute()
        assert len(executed) == 0
        assert agent.pending_count == 1
