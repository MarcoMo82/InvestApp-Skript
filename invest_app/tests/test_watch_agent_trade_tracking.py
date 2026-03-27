"""
Tests für WatchAgent – Trade-Tracking:
  - sync_positions_from_mt5: DB-Aktualisierung, keine aktiven SL-Eingriffe
  - _handle_trade_closed: Exit-Details + Learning-Trigger
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from agents.watch_agent import WatchAgent
from data.order_db import OrderDB


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_order_db() -> OrderDB:
    return OrderDB(":memory:")


def _make_agent(order_db: OrderDB, connector=None, learning_agent=None) -> WatchAgent:
    if connector is None:
        connector = MagicMock()
        connector.get_ohlcv.return_value = MagicMock(empty=True)
    return WatchAgent(
        connector=connector,
        order_db=order_db,
        learning_agent=learning_agent,
    )


def _seed_open_order(order_db: OrderDB, ticket: int = 1001, symbol: str = "EURUSD") -> str:
    """Legt eine offene Order in der DB an."""
    oid = order_db.add_order(
        symbol=symbol,
        direction="buy",
        sl=1.0800,
        tp=1.0900,
        confidence=85.0,
        lot_size=0.01,
        entry_price=1.0850,
        atr_value=0.0012,
    )
    order_db.set_mt5_ticket(oid, ticket)
    return oid


# ---------------------------------------------------------------------------
# sync_positions_from_mt5 – kein aktiver SL-Eingriff
# ---------------------------------------------------------------------------

class TestSyncPositionsNOActiveSLManagement:
    def test_no_modify_position_called(self):
        """Python greift NICHT in SL ein – nur DB wird aktualisiert."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=2001)

        connector = MagicMock()
        connector.get_open_positions.return_value = [
            {
                "ticket": 2001,
                "symbol": "EURUSD",
                "direction": "buy",
                "type": "long",
                "current_price": 1.0860,
                "sl": 1.0820,  # EA hat SL bereits angepasst
                "tp": 1.0900,
                "volume": 0.01,
                "open_price": 1.0850,
                "profit": 1.0,
            }
        ]

        agent = _make_agent(order_db, connector=connector)
        agent.sync_positions_from_mt5()

        # modify_position darf NICHT aufgerufen worden sein
        connector.modify_position.assert_not_called()

    def test_updates_max_price_for_long(self):
        """max_price_reached wird für LONG-Trade korrekt gesetzt."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=2002)

        connector = MagicMock()
        connector.get_open_positions.return_value = [
            {
                "ticket": 2002,
                "symbol": "EURUSD",
                "direction": "buy",
                "type": "long",
                "current_price": 1.0870,
                "sl": 1.0850,
                "tp": 1.0900,
                "volume": 0.01,
                "open_price": 1.0850,
                "profit": 2.0,
            }
        ]

        agent = _make_agent(order_db, connector=connector)
        agent.sync_positions_from_mt5()

        order = order_db.get_order_by_ticket(2002)
        assert order["max_price_reached"] == pytest.approx(1.0870)

    def test_updates_min_price_for_short(self):
        """min_price_reached wird für SHORT-Trade korrekt gesetzt."""
        order_db = _make_order_db()
        oid = order_db.add_order(
            symbol="GBPUSD",
            direction="sell",
            sl=1.2700,
            tp=1.2500,
            confidence=82.0,
            lot_size=0.01,
            entry_price=1.2600,
        )
        order_db.set_mt5_ticket(oid, 2003)

        connector = MagicMock()
        connector.get_open_positions.return_value = [
            {
                "ticket": 2003,
                "symbol": "GBPUSD",
                "direction": "sell",
                "type": "short",
                "current_price": 1.2570,
                "sl": 1.2700,
                "tp": 1.2500,
                "volume": 0.01,
                "open_price": 1.2600,
                "profit": 3.0,
            }
        ]

        agent = _make_agent(order_db, connector=connector)
        agent.sync_positions_from_mt5()

        order = order_db.get_order_by_ticket(2003)
        assert order["min_price_reached"] == pytest.approx(1.2570)


# ---------------------------------------------------------------------------
# _handle_trade_closed
# ---------------------------------------------------------------------------

class TestHandleTradeClosed:
    def test_marks_trade_closed_in_db(self):
        """_handle_trade_closed setzt status='closed' und Exit-Felder."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=3001)

        connector = MagicMock()
        connector.get_deals_history.return_value = {
            "exit_price": 1.0900,
            "profit": 5.0,
            "reason": "TP",
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }

        agent = _make_agent(order_db, connector=connector)
        agent._handle_trade_closed(3001)

        order = order_db.get_order_by_ticket(3001)
        assert order["status"] == "closed"
        assert order["exit_reason"] == "TP"
        assert order["pnl_currency"] == pytest.approx(5.0)

    def test_handles_missing_history_gracefully(self):
        """Auch ohne MT5-History wird der Trade als closed markiert."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=3002)

        connector = MagicMock()
        connector.get_deals_history.return_value = None

        agent = _make_agent(order_db, connector=connector)
        agent._handle_trade_closed(3002)

        order = order_db.get_order_by_ticket(3002)
        assert order["status"] == "closed"

    def test_triggers_learning_agent(self):
        """_trigger_learning_analysis wird nach Trade-Schließung aufgerufen."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=3003)

        connector = MagicMock()
        connector.get_deals_history.return_value = None

        mock_learning = MagicMock()
        agent = _make_agent(order_db, connector=connector, learning_agent=mock_learning)
        agent._handle_trade_closed(3003)

        mock_learning.analyze_closed_trade.assert_called_once_with(3003)
        mock_learning.check_and_apply_config_adjustments.assert_called_once()

    def test_no_error_when_connector_has_no_history_method(self):
        """Kein Fehler wenn connector get_deals_history nicht implementiert."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=3004)

        connector = MagicMock(spec=[])  # kein get_deals_history
        agent = _make_agent(order_db, connector=connector)
        # Darf keine Exception werfen
        agent._handle_trade_closed(3004)


# ---------------------------------------------------------------------------
# sync: geschlossene Tickets erkennen
# ---------------------------------------------------------------------------

class TestSyncDetectsClosedTrades:
    def test_closed_ticket_triggers_handle(self):
        """Ticket das nicht mehr in MT5 ist → _handle_trade_closed wird aufgerufen."""
        order_db = _make_order_db()
        _seed_open_order(order_db, ticket=4001)

        connector = MagicMock()
        # MT5 liefert leere Liste → alle DB-Tickets als geschlossen erkannt
        connector.get_open_positions.return_value = []
        connector.get_deals_history.return_value = None

        agent = _make_agent(order_db, connector=connector)

        with patch.object(agent, "_handle_trade_closed") as mock_close:
            agent.sync_positions_from_mt5()
            mock_close.assert_called_once_with(4001)
