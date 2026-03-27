"""Tests für OrderDB – neue Schema-Spalten und Trade-Begleitungs-Methoden."""
import json
from datetime import datetime, timezone

import pytest

from data.order_db import OrderDB


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """In-Memory OrderDB für jeden Test frisch."""
    return OrderDB(":memory:")


def _add_open_order(db: OrderDB, symbol: str = "EURUSD", ticket: int = 1001) -> str:
    """Hilfsfunktion: legt eine offene Order an."""
    oid = db.add_order(
        symbol=symbol,
        direction="buy",
        sl=1.0800,
        tp=1.0900,
        confidence=85.0,
        lot_size=0.01,
        entry_price=1.0850,
        crv=2.0,
        entry_type="pullback",
        atr_value=0.0012,
        atr_pct=0.11,
        rsi_value=45.0,
        rsi_zone="neutral",
        volatility_phase="normal",
        macro_bias="BULLISH",
        trend_direction="LONG",
    )
    db.set_mt5_ticket(oid, ticket)
    return oid


# ---------------------------------------------------------------------------
# Schema-Tests: neue Spalten vorhanden
# ---------------------------------------------------------------------------

class TestNewSchemaColumns:
    def test_new_context_columns_exist(self, db):
        """Alle Trade-Kontext-Spalten werden beim Anlegen gespeichert."""
        oid = _add_open_order(db)
        order = db.get_open_orders()[0]
        assert order["entry_type"] == "pullback"
        assert order["atr_value"] == pytest.approx(0.0012)
        assert order["atr_pct"] == pytest.approx(0.11)
        assert order["rsi_value"] == pytest.approx(45.0)
        assert order["rsi_zone"] == "neutral"
        assert order["volatility_phase"] == "normal"
        assert order["macro_bias"] == "BULLISH"
        assert order["trend_direction"] == "LONG"

    def test_learning_columns_default(self, db):
        """learning_analyzed startet bei 0, learning_notes bei NULL."""
        _add_open_order(db)
        order = db.get_open_orders()[0]
        assert order["learning_analyzed"] == 0
        assert order["learning_notes"] is None

    def test_progress_columns_default_null(self, db):
        """Trade-Verlaufs-Spalten starten bei NULL."""
        _add_open_order(db)
        order = db.get_open_orders()[0]
        assert order["max_price_reached"] is None
        assert order["min_price_reached"] is None
        assert order["last_sl"] is None
        assert order["last_checked_at"] is None


# ---------------------------------------------------------------------------
# update_trade_progress
# ---------------------------------------------------------------------------

class TestUpdateTradeProgress:
    def test_updates_max_min_price_and_sl(self, db):
        _add_open_order(db, ticket=2001)
        ts = datetime.now(timezone.utc).isoformat()
        db.update_trade_progress(
            ticket=2001,
            max_price=1.0870,
            min_price=1.0840,
            last_sl=1.0820,
            last_checked_at=ts,
        )
        order = db.get_order_by_ticket(2001)
        assert order["max_price_reached"] == pytest.approx(1.0870)
        assert order["min_price_reached"] == pytest.approx(1.0840)
        assert order["last_sl"] == pytest.approx(1.0820)
        assert order["last_checked_at"] == ts

    def test_update_unknown_ticket_does_not_raise(self, db):
        """Update auf nicht existierendes Ticket wirft keine Exception."""
        db.update_trade_progress(
            ticket=9999,
            max_price=1.0,
            min_price=1.0,
            last_sl=1.0,
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# mark_trade_closed
# ---------------------------------------------------------------------------

class TestMarkTradeClosed:
    def test_marks_status_closed(self, db):
        _add_open_order(db, ticket=3001)
        closed_at = datetime.now(timezone.utc).isoformat()
        db.mark_trade_closed(
            ticket=3001,
            exit_price=1.0890,
            exit_reason="TP",
            pnl_pips=40.0,
            pnl_currency=4.0,
            closed_at=closed_at,
        )
        order = db.get_order_by_ticket(3001)
        assert order["status"] == "closed"
        assert order["exit_price"] == pytest.approx(1.0890)
        assert order["exit_reason"] == "TP"
        assert order["pnl_pips"] == pytest.approx(40.0)
        assert order["pnl_currency"] == pytest.approx(4.0)

    def test_sl_exit_reason(self, db):
        _add_open_order(db, ticket=3002)
        closed_at = datetime.now(timezone.utc).isoformat()
        db.mark_trade_closed(3002, 1.0810, "SL", -40.0, -4.0, closed_at)
        order = db.get_order_by_ticket(3002)
        assert order["exit_reason"] == "SL"
        assert order["pnl_pips"] == pytest.approx(-40.0)


# ---------------------------------------------------------------------------
# get_closed_unanalyzed_trades
# ---------------------------------------------------------------------------

class TestGetClosedUnanalyzedTrades:
    def test_returns_unanalyzed_closed_trades(self, db):
        _add_open_order(db, ticket=4001)
        closed_at = datetime.now(timezone.utc).isoformat()
        db.mark_trade_closed(4001, 1.0890, "TP", 40.0, 4.0, closed_at)
        unanalyzed = db.get_closed_unanalyzed_trades()
        assert len(unanalyzed) == 1
        assert unanalyzed[0]["mt5_ticket"] == 4001

    def test_open_trades_not_included(self, db):
        _add_open_order(db, ticket=4002)
        unanalyzed = db.get_closed_unanalyzed_trades()
        assert len(unanalyzed) == 0

    def test_analyzed_trades_not_included(self, db):
        _add_open_order(db, ticket=4003)
        closed_at = datetime.now(timezone.utc).isoformat()
        db.mark_trade_closed(4003, 1.0890, "TP", 40.0, 4.0, closed_at)
        db.mark_learning_analyzed(4003, {"won": True})
        unanalyzed = db.get_closed_unanalyzed_trades()
        assert len(unanalyzed) == 0


# ---------------------------------------------------------------------------
# mark_learning_analyzed
# ---------------------------------------------------------------------------

class TestMarkLearningAnalyzed:
    def test_sets_flag_and_notes(self, db):
        _add_open_order(db, ticket=5001)
        closed_at = datetime.now(timezone.utc).isoformat()
        db.mark_trade_closed(5001, 1.0890, "TP", 40.0, 4.0, closed_at)
        notes = {"won": True, "max_favorable_atr": 1.5}
        db.mark_learning_analyzed(5001, notes)

        order = db.get_order_by_ticket(5001)
        assert order["learning_analyzed"] == 1
        loaded_notes = json.loads(order["learning_notes"])
        assert loaded_notes["won"] is True
        assert loaded_notes["max_favorable_atr"] == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# get_trade_context
# ---------------------------------------------------------------------------

class TestGetTradeContext:
    def test_returns_full_record(self, db):
        _add_open_order(db, ticket=6001)
        ctx = db.get_trade_context(6001)
        assert ctx is not None
        assert ctx["symbol"] == "EURUSD"
        assert ctx["entry_type"] == "pullback"
        assert ctx["macro_bias"] == "BULLISH"

    def test_returns_none_for_unknown_ticket(self, db):
        assert db.get_trade_context(9999) is None


# ---------------------------------------------------------------------------
# get_open_tickets
# ---------------------------------------------------------------------------

class TestGetOpenTickets:
    def test_returns_list(self, db):
        _add_open_order(db, ticket=7001)
        _add_open_order(db, symbol="GBPUSD", ticket=7002)
        tickets = db.get_open_tickets()
        assert isinstance(tickets, list)
        assert 7001 in tickets
        assert 7002 in tickets

    def test_empty_when_no_open_orders(self, db):
        assert db.get_open_tickets() == []
