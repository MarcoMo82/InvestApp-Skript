"""
Tests für Trade-Execution im Orchestrator.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from models.signal import Signal, SignalStatus, Direction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    cfg = SimpleNamespace(
        trading_mode="demo",
        min_confidence_score=80.0,
        max_daily_loss=0.05,
        htf_timeframe="15m",
        htf_bars=200,
        entry_timeframe="5m",
        entry_bars=100,
        all_symbols=["EURUSD"],
        cycle_interval_minutes=5,
    )
    return cfg


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_daily_pnl.return_value = 0.0
    db.get_open_trades.return_value = []
    return db


@pytest.fixture
def mock_connector():
    connector = MagicMock()
    connector.get_account_balance.return_value = 10000.0
    connector.get_open_positions.return_value = []

    dummy_ohlcv = pd.DataFrame(
        {
            "open": [1.1] * 50,
            "high": [1.12] * 50,
            "low": [1.09] * 50,
            "close": [1.105] * 50,
            "volume": [1000] * 50,
        },
        index=pd.date_range("2026-01-01", periods=50, freq="15min"),
    )
    connector.get_ohlcv.return_value = dummy_ohlcv
    connector.get_current_price.return_value = {"bid": 1.1045, "ask": 1.1050}
    return connector


def _make_orchestrator(config, connector, mock_db):
    """Baut einen Orchestrator mit vollständig gemockten Agenten."""
    from agents.orchestrator import Orchestrator

    def _agent_mock(return_value: dict) -> MagicMock:
        m = MagicMock()
        m.run.return_value = return_value
        return m

    orch = Orchestrator(
        config=config,
        connector=connector,
        macro_agent=_agent_mock({"trading_allowed": True, "macro_bias": "bullish", "event_risk": "low"}),
        trend_agent=_agent_mock({"direction": "long", "structure_status": "bullish intact"}),
        volatility_agent=_agent_mock({"setup_allowed": True, "atr_value": 0.0015}),
        level_agent=_agent_mock({"nearest_level": 1.1000}),
        entry_agent=_agent_mock({"entry_found": True, "entry_price": 1.1050}),
        risk_agent=_agent_mock({
            "trade_allowed": True,
            "stop_loss": 1.0990,
            "take_profit": 1.1170,
            "crv": 2.0,
            "lot_size": 0.1,
        }),
        validation_agent=_agent_mock({"validated": True, "confidence_score": 85.0, "summary": "ok", "pros": [], "cons": []}),
        reporting_agent=_agent_mock({}),
        database=mock_db,
    )
    return orch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_approved_signal_triggers_order(mock_db, mock_connector, config):
    """Approved Signal → place_order wird aufgerufen und Trade in DB gespeichert."""
    mock_connector.place_order.return_value = 12345

    orch = _make_orchestrator(config, mock_connector, mock_db)
    signals = orch.run_cycle()

    approved = [s for s in signals if s.status == SignalStatus.APPROVED]
    assert len(approved) == 1, "Es sollte genau ein approved Signal geben"

    mock_connector.place_order.assert_called_once()
    mock_db.save_trade.assert_called_once()

    saved_trade = mock_db.save_trade.call_args[0][0]
    assert saved_trade.mt5_ticket == 12345
    assert saved_trade.instrument == "EURUSD"


def test_rejected_signal_no_order(mock_db, mock_connector, config):
    """Wenn Validation rejected → place_order wird NICHT aufgerufen."""
    from agents.orchestrator import Orchestrator

    def _agent_mock(return_value: dict) -> MagicMock:
        m = MagicMock()
        m.run.return_value = return_value
        return m

    orch = Orchestrator(
        config=config,
        connector=mock_connector,
        macro_agent=_agent_mock({"trading_allowed": True, "macro_bias": "bearish", "event_risk": "low"}),
        trend_agent=_agent_mock({"direction": "long", "structure_status": "ok"}),
        volatility_agent=_agent_mock({"setup_allowed": True, "atr_value": 0.001}),
        level_agent=_agent_mock({"nearest_level": 1.1000}),
        entry_agent=_agent_mock({"entry_found": True, "entry_price": 1.1050}),
        risk_agent=_agent_mock({"trade_allowed": True, "stop_loss": 1.099, "take_profit": 1.117, "crv": 2.0, "lot_size": 0.1}),
        # Validation schlägt fehl
        validation_agent=_agent_mock({"validated": False, "confidence_score": 60.0, "summary": "weak", "pros": [], "cons": []}),
        reporting_agent=_agent_mock({}),
        database=mock_db,
    )

    signals = orch.run_cycle()

    mock_connector.place_order.assert_not_called()
    mock_db.save_trade.assert_not_called()


def test_failed_order_does_not_save_trade(mock_db, mock_connector, config):
    """Wenn place_order None zurückgibt → kein save_trade."""
    mock_connector.place_order.return_value = None

    orch = _make_orchestrator(config, mock_connector, mock_db)
    orch.run_cycle()

    mock_connector.place_order.assert_called_once()
    mock_db.save_trade.assert_not_called()


def test_daily_loss_limit_stops_trading(mock_db, mock_connector, config):
    """Bei überschrittenem Daily Loss: run_cycle gibt leere Liste zurück."""
    mock_db.get_daily_pnl.return_value = -600.0  # 6 % von 10 000 → über 5 %

    orch = _make_orchestrator(config, mock_connector, mock_db)
    signals = orch.run_cycle()

    assert signals == [], "Bei überschrittenem Limit soll run_cycle [] zurückgeben"
    mock_connector.place_order.assert_not_called()


def test_analysis_mode_no_order(mock_db, mock_connector, config):
    """Im Modus 'analysis' darf kein Trade ausgeführt werden."""
    config.trading_mode = "analysis"
    mock_connector.place_order.return_value = 99999

    orch = _make_orchestrator(config, mock_connector, mock_db)
    orch.run_cycle()

    mock_connector.place_order.assert_not_called()
