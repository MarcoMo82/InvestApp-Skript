"""Tests für die Database-Klasse."""
import pytest
from datetime import datetime
from pathlib import Path

from utils.database import Database
from models.signal import Signal, Direction, SignalStatus


class TestDatabase:
    @pytest.fixture
    def db(self, tmp_path):
        db_path = tmp_path / "test.db"
        return Database(db_path)

    def test_save_and_retrieve_signal(self, db):
        signal = Signal(
            instrument="AAPL",
            direction=Direction.LONG,
            entry_price=150.0,
            stop_loss=147.0,
            take_profit=156.0,
            crv=2.0,
            lot_size=0.1,
            confidence_score=85.0,
            status=SignalStatus.APPROVED,
            trend_status="bullish structure intact",
            macro_status="bullish",
            reasoning="Test signal",
        )
        db.save_signal(signal)
        signals = db.get_recent_signals(hours=24)
        assert len(signals) >= 1
        assert signals[0]["instrument"] == "AAPL"

    def test_save_signal_stores_correct_fields(self, db):
        signal = Signal(
            instrument="EURUSD",
            direction=Direction.SHORT,
            entry_price=1.0800,
            stop_loss=1.0840,
            take_profit=1.0720,
            crv=2.0,
            lot_size=0.5,
            confidence_score=82.5,
            status=SignalStatus.APPROVED,
        )
        db.save_signal(signal)
        signals = db.get_recent_signals(hours=24, min_confidence=80.0)
        assert len(signals) >= 1
        found = next((s for s in signals if s["instrument"] == "EURUSD"), None)
        assert found is not None
        assert found["confidence_score"] == pytest.approx(82.5)

    def test_daily_pnl_empty_db(self, db):
        pnl = db.get_daily_pnl()
        assert pnl == pytest.approx(0.0)

    def test_get_recent_signals_empty(self, db):
        signals = db.get_recent_signals(hours=24)
        assert signals == []

    def test_min_confidence_filter(self, db):
        """Signale unter min_confidence werden nicht zurückgegeben."""
        low_conf = Signal(
            instrument="MSFT",
            direction=Direction.LONG,
            entry_price=200.0,
            stop_loss=196.0,
            take_profit=208.0,
            crv=2.0,
            confidence_score=50.0,
            status=SignalStatus.REJECTED,
        )
        db.save_signal(low_conf)
        signals = db.get_recent_signals(hours=24, min_confidence=80.0)
        instruments = [s["instrument"] for s in signals]
        assert "MSFT" not in instruments

    def test_open_trades_empty(self, db):
        trades = db.get_open_trades()
        assert trades == []

    def test_get_performance_stats_empty(self, db):
        stats = db.get_performance_stats(days=7)
        assert isinstance(stats, dict)

    def test_multiple_signals_saved(self, db):
        for i, instrument in enumerate(["AAPL", "MSFT", "GOOGL"]):
            signal = Signal(
                instrument=instrument,
                direction=Direction.LONG,
                entry_price=100.0 + i * 10,
                stop_loss=98.0 + i * 10,
                take_profit=106.0 + i * 10,
                crv=2.0,
                confidence_score=85.0,
                status=SignalStatus.APPROVED,
            )
            db.save_signal(signal)

        signals = db.get_recent_signals(hours=24)
        assert len(signals) == 3
