"""
Tests für LearningAgent – Post-Trade-Analyse:
  - analyze_closed_trade: ATR-Exkursion, Confidence-Accuracy
  - check_and_apply_config_adjustments: Muster ≥ 10 → Config-Anpassung
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.learning_agent import LearningAgent


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_trade_ctx(
    ticket: int = 1001,
    symbol: str = "EURUSD",
    direction: str = "LONG",
    entry: float = 1.0850,
    max_price: float = 1.0890,
    min_price: float = 1.0830,
    atr: float = 0.0012,
    confidence: float = 85,
    pnl_pips: float = 40.0,
    exit_reason: str = "TP",
    entry_type: str = "pullback",
    rsi_zone: str = "neutral",
    volatility_phase: str = "normal",
) -> dict:
    return {
        "mt5_ticket": ticket,
        "symbol": symbol,
        "trend_direction": direction,
        "direction": "buy" if direction == "LONG" else "sell",
        "entry_price": entry,
        "max_price_reached": max_price,
        "min_price_reached": min_price,
        "atr_value": atr,
        "confidence": confidence,
        "pnl_pips": pnl_pips,
        "exit_reason": exit_reason,
        "entry_type": entry_type,
        "rsi_zone": rsi_zone,
        "volatility_phase": volatility_phase,
        "learning_analyzed": 0,
    }


def _make_order_db_mock(trade_ctx: dict, unanalyzed: list = None) -> MagicMock:
    mock = MagicMock()
    mock.get_trade_context.return_value = trade_ctx
    mock.get_closed_unanalyzed_trades.return_value = unanalyzed or []
    return mock


# ---------------------------------------------------------------------------
# analyze_closed_trade
# ---------------------------------------------------------------------------

class TestAnalyzeClosedTrade:
    def test_returns_empty_without_order_db(self):
        agent = LearningAgent()
        result = agent.analyze_closed_trade(1001)
        assert result == {}

    def test_returns_empty_for_unknown_ticket(self):
        mock_db = _make_order_db_mock(None)
        agent = LearningAgent(order_db=mock_db)
        result = agent.analyze_closed_trade(9999)
        assert result == {}

    def test_won_flag_set_correctly(self):
        ctx = _make_trade_ctx(pnl_pips=40.0, confidence=85)
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        assert result["won"] is True

    def test_lost_flag_set_correctly(self):
        ctx = _make_trade_ctx(pnl_pips=-20.0, confidence=85)
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        assert result["won"] is False

    def test_max_favorable_atr_long(self):
        """LONG: max_favorable = (max_price - entry) / atr"""
        ctx = _make_trade_ctx(
            direction="LONG", entry=1.0850, max_price=1.0874, atr=0.0012
        )
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        expected = (1.0874 - 1.0850) / 0.0012
        assert result["max_favorable_atr"] == pytest.approx(expected, rel=1e-3)

    def test_max_adverse_atr_long(self):
        """LONG: adverse = (entry - min_price) / atr"""
        ctx = _make_trade_ctx(
            direction="LONG", entry=1.0850, min_price=1.0838, atr=0.0012
        )
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        expected = (1.0850 - 1.0838) / 0.0012
        assert result["max_adverse_atr"] == pytest.approx(expected, rel=1e-3)

    def test_max_favorable_atr_short(self):
        """SHORT: max_favorable = (entry - min_price) / atr"""
        ctx = _make_trade_ctx(
            direction="SHORT", entry=1.2600, min_price=1.2560, max_price=1.2620, atr=0.0015
        )
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        expected = round((1.2600 - 1.2560) / 0.0015, 2)
        assert result["max_favorable_atr"] == pytest.approx(expected, rel=1e-2)

    def test_confidence_accurate_when_high_conf_and_win(self):
        ctx = _make_trade_ctx(confidence=90, pnl_pips=30)
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        assert result["confidence_accurate"] is True

    def test_confidence_accurate_false_when_high_conf_and_loss(self):
        ctx = _make_trade_ctx(confidence=90, pnl_pips=-20)
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        assert result["confidence_accurate"] is False

    def test_pattern_key_structure(self):
        ctx = _make_trade_ctx(
            symbol="GBPUSD", entry_type="breakout", rsi_zone="overbought", volatility_phase="high"
        )
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        assert "GBPUSD" in result["pattern_key"]
        assert "breakout" in result["pattern_key"]

    def test_mark_learning_analyzed_called(self):
        ctx = _make_trade_ctx(pnl_pips=40)
        mock_db = _make_order_db_mock(ctx)
        agent = LearningAgent(order_db=mock_db)
        agent.analyze_closed_trade(1001)
        mock_db.mark_learning_analyzed.assert_called_once()
        call_ticket = mock_db.mark_learning_analyzed.call_args[0][0]
        assert call_ticket == 1001

    def test_exit_reason_in_result(self):
        ctx = _make_trade_ctx(exit_reason="SL")
        agent = LearningAgent(order_db=_make_order_db_mock(ctx))
        result = agent.analyze_closed_trade(1001)
        assert result["exit_reason"] == "SL"


# ---------------------------------------------------------------------------
# check_and_apply_config_adjustments
# ---------------------------------------------------------------------------

class TestCheckAndApplyConfigAdjustments:
    def test_no_adjustment_below_threshold(self):
        """Weniger als 10 Verluste → keine Anpassung."""
        losses = [
            {
                "symbol": "EURUSD",
                "entry_type": "pullback",
                "rsi_zone": "neutral",
                "pnl_pips": -10.0,
            }
            for _ in range(9)
        ]
        mock_db = MagicMock()
        mock_db.get_closed_unanalyzed_trades.return_value = losses
        agent = LearningAgent(order_db=mock_db, config={"pipeline": {"confidence_threshold": 80}})
        result = agent.check_and_apply_config_adjustments()
        assert result == []

    def test_adjustment_at_10_losses(self, tmp_path):
        """Genau 10 Verluste mit gleichem Muster → Confidence-Schwelle wird erhöht."""
        # Config-Datei anlegen
        config_file = tmp_path / "config.json"
        config_data = {"pipeline": {"confidence_threshold": 80}}
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        losses = [
            {
                "symbol": "EURUSD",
                "entry_type": "pullback",
                "rsi_zone": "neutral",
                "volatility_phase": "normal",
                "pnl_pips": -10.0,
            }
            for _ in range(10)
        ]
        mock_db = MagicMock()
        mock_db.get_closed_unanalyzed_trades.return_value = losses

        agent = LearningAgent(
            order_db=mock_db,
            config={"pipeline": {"confidence_threshold": 80}},
            config_path=config_file,
        )
        adjustments = agent.check_and_apply_config_adjustments()
        assert len(adjustments) == 1
        assert "EURUSD" in adjustments[0]["pattern"]
        assert adjustments[0]["occurrences"] == 10

    def test_max_threshold_capped_at_95(self, tmp_path):
        """Schwelle wird nicht über 95 erhöht."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"pipeline": {"confidence_threshold": 94}}))

        losses = [
            {
                "symbol": "EURUSD",
                "entry_type": "pullback",
                "rsi_zone": "neutral",
                "pnl_pips": -10.0,
            }
            for _ in range(12)
        ]
        mock_db = MagicMock()
        mock_db.get_closed_unanalyzed_trades.return_value = losses

        agent = LearningAgent(
            order_db=mock_db,
            config={"pipeline": {"confidence_threshold": 94}},
            config_path=config_file,
        )
        adjustments = agent.check_and_apply_config_adjustments()
        # Neue Schwelle = min(94 + 5, 95) = 95
        assert "95" in adjustments[0]["adjustment"]

    def test_wins_do_not_count_as_loss_pattern(self):
        """Gewinn-Trades erzeugen kein Verlust-Muster."""
        trades = [
            {
                "symbol": "EURUSD",
                "entry_type": "pullback",
                "rsi_zone": "neutral",
                "pnl_pips": 20.0,  # Gewinn
            }
            for _ in range(15)
        ]
        mock_db = MagicMock()
        mock_db.get_closed_unanalyzed_trades.return_value = trades
        agent = LearningAgent(order_db=mock_db, config={"pipeline": {"confidence_threshold": 80}})
        result = agent.check_and_apply_config_adjustments()
        assert result == []

    def test_returns_empty_without_order_db(self):
        agent = LearningAgent()
        result = agent.check_and_apply_config_adjustments()
        assert result == []
