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
        signal = {"instrument": "EURUSD", "entry_type": "rejection", "direction": "long"}
        assert agent._check_entry_condition(signal, ohlcv) is True

    def test_rejection_buy_bearish_candle_no_entry(self):
        """Rejection Long: letzte Kerze bearisch → kein Entry."""
        n = 30
        ohlcv = _make_ohlcv(n=n, price=1.1000)
        ohlcv.at[ohlcv.index[-1], "open"] = 1.1010
        ohlcv.at[ohlcv.index[-1], "close"] = 1.0990  # close < open
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "rejection", "direction": "long"}
        assert agent._check_entry_condition(signal, ohlcv) is False

    def test_rejection_sell_bearish_candle(self):
        """Rejection Short: letzte Kerze bearisch → Entry."""
        n = 30
        ohlcv = _make_ohlcv(n=n, price=1.1000)
        ohlcv.at[ohlcv.index[-1], "open"] = 1.1010
        ohlcv.at[ohlcv.index[-1], "close"] = 1.0990  # close < open
        agent = WatchAgent(connector=_make_connector(ohlcv))
        signal = {"instrument": "EURUSD", "entry_type": "rejection", "direction": "short"}
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


def _make_ohlcv_atr(n: int = 20, price: float = 1.1000, atr_range: float = 0.002) -> pd.DataFrame:
    """OHLCV mit realistischer ATR für Trailing-Stop-Tests."""
    return pd.DataFrame({
        "open": [price] * n,
        "high": [price + atr_range] * n,
        "low": [price - atr_range] * n,
        "close": [price] * n,
        "volume": [1000] * n,
    })


class TestBreakevenLogic:
    def test_breakeven_set_when_1to1_reached_long(self):
        """Long: Preis hat 1:1 CRV erreicht → SL wird auf Entry-Preis gesetzt."""
        connector = MagicMock()
        connector.get_tick.return_value = {"bid": 1.1040, "ask": 1.1042}
        connector.get_ohlcv.return_value = _make_ohlcv_atr(n=20, price=1.1020, atr_range=0.0010)
        connector.modify_position.return_value = True

        db = MagicMock()
        db.get_open_trades.return_value = [{
            "mt5_ticket": 111,
            "instrument": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "sl": 1.0980,  # SL 20 Pips unter Entry
            "tp": 1.1040,
        }]

        risk_agent = MagicMock()
        risk_agent.calculate_trailing_stop.return_value = 1.0980  # kein Trailing-Update

        agent = WatchAgent(connector=connector, db=db, risk_agent=risk_agent)
        agent.check_and_execute()

        # modify_position muss mit entry_price=1.1000 aufgerufen worden sein
        connector.modify_position.assert_called_once_with(111, 1.1000)

    def test_breakeven_not_set_when_sl_already_above_entry(self):
        """Long: SL bereits über Entry-Preis → kein weiterer Breakeven-Aufruf."""
        connector = MagicMock()
        connector.get_tick.return_value = {"bid": 1.1040, "ask": 1.1042}
        connector.get_ohlcv.return_value = _make_ohlcv_atr(n=20, price=1.1020, atr_range=0.0010)
        connector.modify_position.return_value = True

        db = MagicMock()
        db.get_open_trades.return_value = [{
            "mt5_ticket": 222,
            "instrument": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "sl": 1.1005,  # SL bereits über Entry → Breakeven schon gesetzt
            "tp": 1.1040,
        }]

        risk_agent = MagicMock()
        risk_agent.calculate_trailing_stop.return_value = 1.1005

        agent = WatchAgent(connector=connector, db=db, risk_agent=risk_agent)
        agent.check_and_execute()

        # modify_position darf nicht für Breakeven aufgerufen werden
        for call in connector.modify_position.call_args_list:
            assert call.args[1] != 1.1000

    def test_trailing_stop_updates_sl_when_improved_long(self):
        """Long: Trailing Stop verbessert SL → modify_position wird aufgerufen."""
        connector = MagicMock()
        connector.get_tick.return_value = {"bid": 1.1060, "ask": 1.1062}
        connector.get_ohlcv.return_value = _make_ohlcv_atr(n=20, price=1.1040, atr_range=0.0010)
        connector.modify_position.return_value = True

        db = MagicMock()
        db.get_open_trades.return_value = [{
            "mt5_ticket": 333,
            "instrument": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "sl": 1.1010,  # SL schon über Entry
            "tp": 1.1040,
        }]

        new_trailing_sl = 1.1030
        risk_agent = MagicMock()
        risk_agent.calculate_trailing_stop.return_value = new_trailing_sl

        agent = WatchAgent(connector=connector, db=db, risk_agent=risk_agent)
        agent.check_and_execute()

        connector.modify_position.assert_called_once_with(333, new_trailing_sl)

    def test_trailing_stop_skipped_without_risk_agent(self):
        """Kein risk_agent → kein Positions-Monitoring, kein Absturz."""
        connector = MagicMock()
        db = MagicMock()
        db.get_open_trades.return_value = [{
            "mt5_ticket": 444,
            "instrument": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "sl": 1.0980,
            "tp": 1.1040,
        }]

        agent = WatchAgent(connector=connector, db=db, risk_agent=None)
        agent.check_and_execute()  # darf nicht crashen

        connector.modify_position.assert_not_called()


class TestCheckAndExecute:
    def test_executed_signal_removed_from_pending(self):
        """Nach Ausführung wird Signal aus der Pending-Liste entfernt."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        connector.place_market_order = MagicMock(return_value=12345)
        agent = WatchAgent(connector=connector, trade_connector=connector)
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

    def test_failed_order_increments_retry_count(self):
        """Schlägt place_market_order fehl → _retry_count wird hochgezählt, Signal bleibt pending."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        connector.place_market_order = MagicMock(return_value=None)  # Fehler simulieren
        agent = WatchAgent(connector=connector, trade_connector=connector)
        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal)

        executed = agent.check_and_execute()

        assert len(executed) == 0
        assert agent.pending_count == 1
        assert signal.get("_retry_count") == 1

    def test_signal_discarded_after_three_failed_retries(self):
        """Nach 3 fehlgeschlagenen Versuchen wird Signal verworfen und aus Pending entfernt."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        connector.place_market_order = MagicMock(return_value=None)
        agent = WatchAgent(connector=connector, trade_connector=connector)
        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal)

        # 3 Versuche durchlaufen
        for _ in range(3):
            agent.check_and_execute()

        assert agent.pending_count == 0
        assert signal.get("_retry_count") == 3

    def test_place_order_blocked_when_no_trade_connector(self):
        """Kein trade_connector → Fallback auf direktes pending_order.json (kein Retry-Zähler)."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        # trade_connector=None simuliert: MT5 nicht verfügbar (yfinance-Fallback)
        agent = WatchAgent(connector=connector, trade_connector=None)
        signal = {"instrument": "EURCHF", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal)

        executed = agent.check_and_execute()

        # Signal wird via pending_order.json-Fallback als ausgeführt markiert
        assert len(executed) == 1
        assert agent.pending_count == 0
        # Kein Retry-Zähler – direkte Datei-Fallback ist kein fehlgeschlagener Versuch
        assert signal.get("_retry_count", 0) == 0

    def test_signal_stays_pending_indefinitely_without_trade_connector(self):
        """Kein trade_connector → Signal wird via Datei-Fallback im ersten Zyklus ausgeführt."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        agent = WatchAgent(connector=connector, trade_connector=None)
        signal = {"instrument": "EURCHF", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal)

        for _ in range(5):
            agent.check_and_execute()

        # Nach erstem Zyklus via Datei-Fallback ausgeführt → pending_count == 0
        assert agent.pending_count == 0
        assert signal.get("_retry_count", 0) == 0

    def test_signal_id_assigned_on_add(self):
        """add_pending_signal weist eindeutige _signal_id zu."""
        agent = WatchAgent(connector=_make_connector())
        s1 = {"instrument": "EURUSD", "entry_type": "market"}
        s2 = {"instrument": "GBPUSD", "entry_type": "market"}
        agent.add_pending_signal(s1)
        agent.add_pending_signal(s2)
        assert "_signal_id" in s1
        assert "_signal_id" in s2
        assert s1["_signal_id"] != s2["_signal_id"]

    def test_race_condition_new_signals_preserved_during_execution(self):
        """Neu hinzugefügte Signale während check_and_execute() werden nicht überschrieben."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)
        connector.place_market_order = MagicMock(return_value=12345)
        agent = WatchAgent(connector=connector, trade_connector=connector)

        signal_a = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal_a)

        # Neues Signal wird während der Ausführung extern hinzugefügt
        signal_b = {"instrument": "GBPUSD", "entry_type": "breakout", "entry_price": 9999.0}

        original_place = agent._place_order

        def place_and_inject(sig):
            ticket = original_place(sig)
            agent.add_pending_signal(signal_b)  # Concurrent-Add simulieren
            return ticket

        agent._place_order = place_and_inject

        executed = agent.check_and_execute()

        assert len(executed) == 1
        assert agent.pending_count == 1  # signal_b muss erhalten bleiben


class TestLazyReconnect:
    def test_try_reconnect_returns_false_without_config(self):
        """_try_reconnect_mt5 gibt False zurück wenn kein Config oder mt5_login."""
        agent = WatchAgent(connector=_make_connector(), trade_connector=None)
        result = agent._try_reconnect_mt5()
        assert result is False
        assert agent.trade_connector is None

    def test_try_reconnect_returns_false_without_mt5_login(self):
        """_try_reconnect_mt5 gibt False zurück wenn mt5_login nicht gesetzt."""
        config = MagicMock()
        config.mt5_login = 0  # falsy
        agent = WatchAgent(connector=_make_connector(), trade_connector=None, config=config)
        result = agent._try_reconnect_mt5()
        assert result is False
        assert agent.trade_connector is None

    def test_place_order_attempts_reconnect_when_no_trade_connector(self):
        """_place_order versucht Reconnect wenn trade_connector=None."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)

        config = MagicMock()
        config.mt5_login = 0  # Reconnect schlägt fehl (kein Login)

        agent = WatchAgent(connector=connector, trade_connector=None, config=config)
        signal = {
            "instrument": "EURUSD",
            "direction": "long",
            "entry_type": "market",
            "entry_price": 1.1000,
            "lot_size": 0.01,
        }
        agent.add_pending_signal(signal)
        executed = agent.check_and_execute()

        # Kein Reconnect möglich → Signal bleibt in Überwachung, kein Retry-Zähler
        assert len(executed) == 0
        assert agent.pending_count == 1
        assert signal.get("_retry_count", 0) == 0

    def test_place_order_succeeds_after_lazy_reconnect(self):
        """_place_order setzt trade_connector nach erfolgreichem Reconnect und führt Order aus."""
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)

        new_trade_conn = MagicMock()
        new_trade_conn.place_market_order = MagicMock(return_value=99999)

        config = MagicMock()
        config.mt5_login = 12345
        config.mt5_password = "pw"
        config.mt5_server = "server"
        config.mt5_path = ""

        agent = WatchAgent(connector=connector, trade_connector=None, config=config)

        # _try_reconnect_mt5 wird überschrieben um MT5-Import zu umgehen
        def fake_reconnect():
            agent.trade_connector = new_trade_conn
            return True

        agent._try_reconnect_mt5 = fake_reconnect

        signal = {
            "instrument": "EURUSD",
            "direction": "long",
            "entry_type": "market",
            "entry_price": 1.1000,
            "lot_size": 0.01,
        }
        agent.add_pending_signal(signal)
        executed = agent.check_and_execute()

        assert len(executed) == 1
        assert agent.pending_count == 0
        new_trade_conn.place_market_order.assert_called_once()


class TestPendingFileTicket:
    def test_file_ticket_sentinel_is_handled_as_executed(self):
        """_PENDING_FILE_TICKET wird in check_and_execute als ausgeführt behandelt (kein Retry)."""
        from agents.watch_agent import _PENDING_FILE_TICKET
        ohlcv = _make_ohlcv(price=1.1000)
        connector = _make_connector(ohlcv)

        agent = WatchAgent(connector=connector, trade_connector=connector)

        # _place_order gibt _PENDING_FILE_TICKET zurück (simuliert file-Fallback)
        agent._place_order = MagicMock(return_value=_PENDING_FILE_TICKET)

        signal = {"instrument": "EURUSD", "entry_type": "market", "entry_price": 1.1000}
        agent.add_pending_signal(signal)
        executed = agent.check_and_execute()

        # Signal wird aus Pending entfernt, kein Retry
        assert len(executed) == 1
        assert agent.pending_count == 0
        assert signal.get("_retry_count", 0) == 0
