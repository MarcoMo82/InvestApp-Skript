"""Tests für den LearningAgent."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.learning_agent import LearningAgent


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_trade(instrument="EURUSD", direction="long", pnl=10.0,
                status="closed", entry=1.08, sl=1.076, tp=1.088):
    return {
        "id": f"t_{instrument}_{pnl}",
        "instrument": instrument,
        "direction": direction,
        "pnl": pnl,
        "status": status,
        "entry_price": entry,
        "sl": sl,
        "tp": tp,
    }


def _winning_trade(**kwargs):
    return _make_trade(pnl=20.0, **kwargs)


def _losing_trade(**kwargs):
    return _make_trade(pnl=-10.0, **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLearningAgentInstantiation:
    def test_basic_instantiation(self):
        agent = LearningAgent()
        assert agent.name == "learning_agent"
        assert agent.db is None

    def test_instantiation_with_db(self, mock_db):
        agent = LearningAgent(db=mock_db)
        assert agent.db is mock_db

    def test_instantiation_with_output_dir(self, tmp_path):
        agent = LearningAgent(output_dir=tmp_path)
        assert agent.output_dir == tmp_path

    def test_inherits_base_agent(self):
        from agents.base_agent import BaseAgent
        agent = LearningAgent()
        assert isinstance(agent, BaseAgent)


class TestRunPostCycleEmptyTrades:
    def test_empty_list_returns_zero_analyzed(self, mock_db):
        mock_db.get_closed_trades.return_value = []
        agent = LearningAgent(db=mock_db)
        result = agent.run_post_cycle([])
        assert result["trades_analyzed"] == 0
        assert result["insights"] == []
        assert result["recommendations"] == []

    def test_empty_list_no_db_returns_zero(self):
        agent = LearningAgent(db=None)
        result = agent.run_post_cycle([])
        assert result["trades_analyzed"] == 0
        assert result["success"] is True

    def test_only_open_trades_returns_zero(self):
        """Offene Trades ohne PnL werden ignoriert."""
        open_trades = [
            {"id": "t1", "instrument": "EURUSD", "direction": "long",
             "pnl": None, "status": "open"},
        ]
        agent = LearningAgent(db=None)
        result = agent.run_post_cycle(open_trades)
        assert result["trades_analyzed"] == 0


class TestRunPostCycleWithTrades:
    def test_winning_trades_analyzed(self, tmp_path):
        trades = [_winning_trade() for _ in range(5)]
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        assert result["trades_analyzed"] == 5
        assert result["success"] is True

    def test_mixed_trades_produces_insights(self, tmp_path):
        trades = [_winning_trade()] * 3 + [_losing_trade()] * 2
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        assert result["trades_analyzed"] == 5
        assert any(i["type"] == "overall_win_rate" for i in result["insights"])

    def test_db_trades_merged_deduped(self, tmp_path, mock_db):
        """Trades aus DB werden zusammengeführt, ohne Duplikate."""
        trade = _winning_trade()
        mock_db.get_closed_trades.return_value = [trade]
        agent = LearningAgent(output_dir=tmp_path, db=mock_db)
        # Übergabe desselben Trades → soll nur 1x gezählt werden
        result = agent.run_post_cycle([trade])
        assert result["trades_analyzed"] == 1

    def test_db_failure_is_tolerated(self, tmp_path):
        """DB-Fehler werden abgefangen, Analyse läuft trotzdem."""
        mock_db = MagicMock()
        mock_db.get_closed_trades.side_effect = RuntimeError("DB down")
        trades = [_winning_trade()]
        agent = LearningAgent(output_dir=tmp_path, db=mock_db)
        result = agent.run_post_cycle(trades)
        assert result["success"] is True
        assert result["trades_analyzed"] == 1


class TestPatternAnalysis:
    def test_overall_win_rate_correct(self, tmp_path):
        trades = [_winning_trade()] * 3 + [_losing_trade()] * 1
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        overall = next(i for i in result["insights"] if i["type"] == "overall_win_rate")
        assert overall["value"] == 75.0
        assert overall["sample_size"] == 4

    def test_win_rate_per_instrument(self, tmp_path):
        trades = [
            _winning_trade(instrument="EURUSD"),
            _winning_trade(instrument="EURUSD"),
            _losing_trade(instrument="GBPUSD"),
        ]
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        instr_insights = [i for i in result["insights"] if i["type"] == "win_rate_by_instrument"]
        instruments = {i["instrument"] for i in instr_insights}
        assert "EURUSD" in instruments
        assert "GBPUSD" in instruments

        eurusd = next(i for i in instr_insights if i["instrument"] == "EURUSD")
        assert eurusd["value"] == 100.0

        gbpusd = next(i for i in instr_insights if i["instrument"] == "GBPUSD")
        assert gbpusd["value"] == 0.0

    def test_win_rate_by_direction(self, tmp_path):
        trades = [
            _winning_trade(direction="long"),
            _winning_trade(direction="long"),
            _losing_trade(direction="short"),
        ]
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        dir_insights = [i for i in result["insights"] if i["type"] == "win_rate_by_direction"]
        long_insight = next(i for i in dir_insights if i["direction"] == "long")
        short_insight = next(i for i in dir_insights if i["direction"] == "short")
        assert long_insight["value"] == 100.0
        assert short_insight["value"] == 0.0

    def test_avg_planned_crv_calculated(self, tmp_path):
        # entry=1.08, sl=1.076 (4 pips), tp=1.096 (16 pips) → CRV=4.0
        trades = [
            _make_trade(entry=1.08, sl=1.076, tp=1.096, direction="long", pnl=10.0),
        ]
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        crv_insight = next(
            (i for i in result["insights"] if i["type"] == "avg_planned_crv"), None
        )
        assert crv_insight is not None
        assert crv_insight["value"] == pytest.approx(4.0, abs=0.01)


class TestRecommendationGeneration:
    def test_low_win_rate_triggers_confidence_increase(self, tmp_path):
        """Win-Rate < 50% mit genug Samples → increase_confidence_threshold."""
        trades = [_losing_trade()] * 7 + [_winning_trade()] * 3
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        recs = result["recommendations"]
        assert any(r["type"] == "increase_confidence_threshold" for r in recs)

    def test_no_recommendation_with_insufficient_samples(self, tmp_path):
        """Weniger als 5 Trades → keine Empfehlung."""
        trades = [_losing_trade()] * 2 + [_winning_trade()] * 1
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        conf_recs = [r for r in result["recommendations"] if r["type"] == "increase_confidence_threshold"]
        assert conf_recs == []

    def test_bad_instrument_recommendation(self, tmp_path):
        """Instrument mit win_rate < 40% und ≥ 3 Trades → avoid_instrument."""
        trades = [_losing_trade(instrument="XAUUSD")] * 4
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        recs = result["recommendations"]
        avoid = [r for r in recs if r["type"] == "avoid_instrument"]
        assert any(r["instrument"] == "XAUUSD" for r in avoid)

    def test_high_win_rate_triggers_crv_review(self, tmp_path):
        """Win-Rate > 65% → CRV-Review empfehlen."""
        trades = [_winning_trade()] * 8 + [_losing_trade()] * 1
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        recs = result["recommendations"]
        assert any(r["type"] == "review_crv" for r in recs)

    def test_direction_bias_detected(self, tmp_path):
        """Großer Unterschied long/short Win-Rate → direction_bias Empfehlung."""
        trades = (
            [_winning_trade(direction="long")] * 4
            + [_losing_trade(direction="short")] * 4
        )
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        recs = result["recommendations"]
        assert any(r["type"] == "direction_bias" for r in recs)


class TestPersistence:
    def test_json_log_written(self, tmp_path):
        trades = [_winning_trade(), _losing_trade()]
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        assert result["log_path"] is not None
        log_file = Path(result["log_path"])
        assert log_file.exists()

    def test_json_log_valid_structure(self, tmp_path):
        trades = [_winning_trade(), _losing_trade()]
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        data = json.loads(Path(result["log_path"]).read_text())
        assert "timestamp" in data
        assert "insights" in data
        assert "recommendations" in data
        assert data["trades_analyzed"] == 2

    def test_no_log_on_empty_trades(self, tmp_path):
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle([])
        assert result["log_path"] is None

    def test_persist_failure_does_not_raise(self, tmp_path):
        """Wenn output_dir nicht schreibbar, kein Absturz."""
        agent = LearningAgent(output_dir=tmp_path, db=None)
        with patch.object(Path, "write_text", side_effect=OSError("no space")):
            result = agent.run_post_cycle([_winning_trade()])
        assert result["success"] is True
        assert result["log_path"] is None


class TestParameterSuggestions:
    def test_empty_trades_returns_empty_suggestions(self, tmp_path):
        """Keine Trades → keine Parameter-Vorschläge."""
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle([])
        assert result["parameter_suggestions"] == []

    def test_parameter_suggestions_key_present(self, tmp_path):
        """parameter_suggestions ist immer im Output vorhanden."""
        agent = LearningAgent(output_dir=tmp_path, db=None)
        trades = [_winning_trade()] * 3 + [_losing_trade()]
        result = agent.run_post_cycle(trades)
        assert "parameter_suggestions" in result

    def test_low_win_rate_triggers_confidence_suggestion(self, tmp_path):
        """Win-Rate < 45% mit ≥ 10 Trades → confidence_threshold-Vorschlag."""
        trades = [_losing_trade()] * 7 + [_winning_trade()] * 3  # 30% win rate
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        suggestions = result["parameter_suggestions"]
        assert any(s["parameter"] == "validation_agent.confidence_threshold" for s in suggestions)

    def test_no_confidence_suggestion_above_win_rate_threshold(self, tmp_path):
        """Win-Rate ≥ 45% → kein confidence_threshold-Vorschlag."""
        trades = [_winning_trade()] * 6 + [_losing_trade()] * 4  # 60% win rate
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        suggestions = result["parameter_suggestions"]
        assert not any(s["parameter"] == "validation_agent.confidence_threshold" for s in suggestions)

    def test_high_entry_slippage_triggers_tolerance_suggestion(self, tmp_path):
        """Slippage > 0.2% → entry_tolerance-Vorschlag."""
        trades = []
        for _ in range(5):
            t = _make_trade()
            t["fill_price"] = t["entry_price"] * 1.003  # 0.3% Slippage
            trades.append(t)
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        suggestions = result["parameter_suggestions"]
        assert any(s["parameter"] == "watch_agent.entry_tolerance" for s in suggestions)

    def test_forex_sl_violations_trigger_suggestion(self, tmp_path):
        """Forex SL > 80 Pips → forex_max_pips-Vorschlag."""
        trades = []
        for _ in range(3):
            t = _make_trade(entry=1.1000, sl=1.0900, tp=1.1300)  # 100 Pips SL > 80
            trades.append(t)
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        suggestions = result["parameter_suggestions"]
        assert any(s["parameter"] == "risk_agent.forex_max_pips" for s in suggestions)

    def test_parameter_suggestions_in_json_log(self, tmp_path):
        """parameter_suggestions werden in JSON-Log geschrieben."""
        import json
        from pathlib import Path
        trades = [_losing_trade()] * 7 + [_winning_trade()] * 3
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.run_post_cycle(trades)
        if result["log_path"]:
            data = json.loads(Path(result["log_path"]).read_text())
            assert "parameter_suggestions" in data


class TestAnalyzeMethod:
    def test_analyze_via_dict(self, tmp_path):
        """analyze() via dict-Interface (BaseAgent-Kompatibilität)."""
        agent = LearningAgent(output_dir=tmp_path, db=None)
        trades = [_winning_trade()] * 3 + [_losing_trade()]
        result = agent.analyze({"recent_trades": trades})
        assert result["trades_analyzed"] == 4
        assert result["success"] is True

    def test_analyze_empty_data(self, tmp_path):
        agent = LearningAgent(output_dir=tmp_path, db=None)
        result = agent.analyze({})
        assert result["trades_analyzed"] == 0

    def test_run_wrapper_calls_analyze(self, tmp_path):
        """BaseAgent.run() delegiert an analyze()."""
        agent = LearningAgent(output_dir=tmp_path, db=None)
        trades = [_winning_trade()]
        result = agent.run({"recent_trades": trades, "symbol": "LEARNING"})
        assert result["success"] is True
        assert "duration_ms" in result
