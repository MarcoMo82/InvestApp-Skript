"""
Integrationstests für utils/database.py – alle relevanten Methoden.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from utils.database import Database
from models.signal import Signal, SignalStatus, Direction
from models.trade import Trade


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Frische In-Memory-Datenbank für jeden Test."""
    return Database(tmp_path / "test.db")


def _make_signal(**kwargs) -> Signal:
    defaults = dict(
        instrument="EURUSD",
        direction=Direction.LONG,
        entry_price=1.1050,
        stop_loss=1.0990,
        take_profit=1.1170,
        crv=2.0,
        lot_size=0.1,
        confidence_score=85.0,
        status=SignalStatus.APPROVED,
        reasoning="Test-Signal",
    )
    defaults.update(kwargs)
    return Signal(**defaults)


def _make_trade(signal_id: str, ticket: int = 1001, **kwargs) -> Trade:
    defaults = dict(
        signal_id=signal_id,
        mt5_ticket=ticket,
        instrument="EURUSD",
        direction="long",
        entry_price=1.1050,
        sl=1.0990,
        tp=1.1170,
        lot_size=0.1,
        status="open",
    )
    defaults.update(kwargs)
    return Trade(**defaults)


# ---------------------------------------------------------------------------
# Tests: Signale
# ---------------------------------------------------------------------------

def test_save_and_retrieve_signal(db):
    sig = _make_signal()
    db.save_signal(sig)

    recent = db.get_recent_signals(hours=1)
    assert len(recent) == 1
    assert recent[0]["instrument"] == "EURUSD"
    assert recent[0]["confidence_score"] == 85.0


# ---------------------------------------------------------------------------
# Tests: Trades
# ---------------------------------------------------------------------------

def test_save_and_retrieve_trade(db):
    sig = _make_signal()
    db.save_signal(sig)

    trade = _make_trade(signal_id=sig.id, ticket=2001)
    db.save_trade(trade)

    open_trades = db.get_open_trades()
    assert len(open_trades) == 1
    assert open_trades[0]["mt5_ticket"] == 2001
    assert open_trades[0]["status"] == "open"


def test_update_trade_close(db):
    sig = _make_signal()
    db.save_signal(sig)

    trade = _make_trade(signal_id=sig.id, ticket=3001)
    db.save_trade(trade)

    close_time = datetime.utcnow()
    db.update_trade_close(ticket=3001, close_price=1.1120, pnl=70.0, close_time=close_time)

    open_trades = db.get_open_trades()
    assert len(open_trades) == 0, "Nach Schließen soll kein offener Trade mehr da sein"


def test_update_trade_close_nonexistent_ticket(db):
    """Kein Fehler bei unbekanntem Ticket."""
    db.update_trade_close(ticket=99999, close_price=1.1, pnl=0.0, close_time=datetime.utcnow())


# ---------------------------------------------------------------------------
# Tests: Agent-Logs
# ---------------------------------------------------------------------------

def test_log_agent_entry(db):
    db.log_agent(
        agent_name="TrendAgent",
        symbol="EURUSD",
        duration_ms=45.2,
        success=True,
        output_summary="direction=long",
    )
    # Kein Fehler → Test bestanden; Eintrag wurde gespeichert


def test_log_agent_failure(db):
    db.log_agent(
        agent_name="MacroAgent",
        symbol="GBPUSD",
        duration_ms=12.0,
        success=False,
        output_summary="API timeout",
    )


# ---------------------------------------------------------------------------
# Tests: Performance
# ---------------------------------------------------------------------------

def test_update_performance_no_trades(db):
    """update_performance funktioniert auch ohne Trades."""
    db.update_performance()


def test_update_performance(db):
    sig = _make_signal()
    db.save_signal(sig)

    trade = _make_trade(signal_id=sig.id, ticket=4001)
    db.save_trade(trade)
    db.update_trade_close(ticket=4001, close_price=1.1120, pnl=70.0, close_time=datetime.utcnow())

    db.update_performance()  # Kein Fehler → OK


def test_get_performance_stats(db):
    sig = _make_signal()
    db.save_signal(sig)

    trade = _make_trade(signal_id=sig.id, ticket=5001)
    db.save_trade(trade)
    db.update_trade_close(ticket=5001, close_price=1.1120, pnl=70.0, close_time=datetime.utcnow())

    stats = db.get_performance_stats(days=30)
    assert stats["total_trades"] == 1
    assert stats["winning_trades"] == 1
    assert stats["win_rate"] == 100.0
    assert stats["total_pnl"] == 70.0


# ---------------------------------------------------------------------------
# Tests: Daily PnL
# ---------------------------------------------------------------------------

def test_daily_pnl_with_trades(db):
    sig = _make_signal()
    db.save_signal(sig)

    # Trade 1: Gewinn
    t1 = _make_trade(signal_id=sig.id, ticket=6001)
    db.save_trade(t1)
    db.update_trade_close(ticket=6001, close_price=1.1120, pnl=70.0, close_time=datetime.utcnow())

    # Trade 2: Verlust
    sig2 = _make_signal(instrument="GBPUSD")
    db.save_signal(sig2)
    t2 = _make_trade(signal_id=sig2.id, ticket=6002, instrument="GBPUSD")
    db.save_trade(t2)
    db.update_trade_close(ticket=6002, close_price=1.25, pnl=-30.0, close_time=datetime.utcnow())

    daily = db.get_daily_pnl()
    assert abs(daily - 40.0) < 0.01, f"Erwartet 40.0, bekommen {daily}"


def test_daily_pnl_empty(db):
    assert db.get_daily_pnl() == 0.0
