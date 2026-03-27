"""Tests für den ValidationAgent – MTF-Konfluenz-Score."""
import pytest
from unittest.mock import MagicMock

from agents.validation_agent import ValidationAgent


def _make_agent() -> ValidationAgent:
    client = MagicMock()
    client.analyze.return_value = (
        '{"confidence_score": 70, "pros": ["Trend klar"], '
        '"cons": [], "validated": false, "summary": "OK"}'
    )
    return ValidationAgent(claude_client=client)


def _make_full_agent_results(
    trend_score: int = 8,
    level_score: int = 80,
    entry_confidence: float = 0.7,
    rsi: float = 50.0,
    vol_approved: bool = True,
    macro_approved: bool = True,
) -> dict:
    return {
        "trend": {"strength_score": trend_score, "trend_score": trend_score},
        "level": {"reaction_score": level_score // 10, "level_score": level_score},
        "entry": {"confidence": entry_confidence},
        "volatility": {"rsi": rsi, "approved": vol_approved, "setup_allowed": vol_approved},
        "macro": {"trading_allowed": macro_approved, "approved": macro_approved},
    }


class TestMTFConfluence:
    def test_confluence_output_keys(self):
        agent = _make_agent()
        results = _make_full_agent_results()
        mtf = agent._calculate_mtf_confluence(results)
        assert "confluence_score" in mtf
        assert "modifier" in mtf
        assert "label" in mtf
        assert "details" in mtf

    def test_triple_confluence_score(self):
        """5–6 Punkte → triple_confluence, modifier = 1.35."""
        agent = _make_agent()
        results = _make_full_agent_results(
            trend_score=8, level_score=80, entry_confidence=0.7,
            rsi=50.0, vol_approved=True, macro_approved=True
        )
        mtf = agent._calculate_mtf_confluence(results)
        assert mtf["confluence_score"] >= 5
        assert mtf["label"] == "triple_confluence"
        assert mtf["modifier"] == pytest.approx(1.35)

    def test_dual_confluence_score(self):
        """3–4 Punkte → dual_confluence, modifier = 1.15."""
        agent = _make_agent()
        # Nur 3 Punkte: Trend ok, Level ok, Macro ok; Entry + Session + RSI nicht
        results = {
            "trend": {"strength_score": 8},
            "level": {"level_score": 80},
            "entry": {"confidence": 0.3},  # nicht ok
            "volatility": {"rsi": 75.0, "approved": False},  # RSI overbought + nicht approved
            "macro": {"trading_allowed": True},
        }
        mtf = agent._calculate_mtf_confluence(results)
        assert mtf["confluence_score"] in (3, 4)
        assert mtf["label"] == "dual_confluence"
        assert mtf["modifier"] == pytest.approx(1.15)

    def test_weak_confluence_score(self):
        """1–2 Punkte → weak_confluence, modifier = 1.0."""
        agent = _make_agent()
        results = {
            "trend": {"strength_score": 5},  # nicht ok (< 7)
            "level": {"level_score": 50},    # nicht ok (< 70)
            "entry": {"confidence": 0.3},    # nicht ok
            "volatility": {"rsi": 50.0, "approved": True},  # +1 Session
            "macro": {"trading_allowed": False},  # nicht ok
        }
        mtf = agent._calculate_mtf_confluence(results)
        # RSI neutral +1, Session +1 = 2 Punkte
        assert mtf["confluence_score"] in (1, 2)
        assert mtf["label"] == "weak_confluence"
        assert mtf["modifier"] == pytest.approx(1.0)

    def test_no_confluence_score(self):
        """0 Punkte → no_confluence, modifier = 0.5 (×0.5 Multiplikation)."""
        agent = _make_agent()
        results = {
            "trend": {"strength_score": 3},
            "level": {"level_score": 30},
            "entry": {"confidence": 0.1},
            "volatility": {"rsi": 80.0, "approved": False},  # RSI overbought, nicht approved
            "macro": {"trading_allowed": False},
        }
        mtf = agent._calculate_mtf_confluence(results)
        assert mtf["confluence_score"] == 0
        assert mtf["label"] == "no_confluence"
        assert mtf["modifier"] == pytest.approx(0.5)

    def test_rsi_neutral_adds_point(self):
        """RSI zwischen 30–70 → +1 Punkt."""
        agent = _make_agent()
        base = {"trend": {}, "level": {}, "entry": {}, "macro": {}}

        for rsi_val in [50.0, 35.0, 65.0]:
            results = {**base, "volatility": {"rsi": rsi_val, "approved": False}}
            mtf = agent._calculate_mtf_confluence(results)
            rsi_detail = any("RSI" in d for d in mtf["details"])
            assert rsi_detail, f"RSI {rsi_val} sollte Konfluenzpunkt geben"

    def test_rsi_overbought_no_point(self):
        """RSI > 70 → kein RSI-Punkt."""
        agent = _make_agent()
        results = {
            "trend": {}, "level": {}, "entry": {},
            "volatility": {"rsi": 80.0, "approved": False},
            "macro": {},
        }
        mtf = agent._calculate_mtf_confluence(results)
        rsi_detail = any("RSI" in d for d in mtf["details"])
        assert not rsi_detail

    def test_confluence_applied_to_confidence_score(self, mock_claude_client):
        """MTF-Modifier wird auf confidence_score angewendet."""
        agent = ValidationAgent(claude_client=mock_claude_client)
        # Mock gibt 75 zurück; mit triple_confluence (+35) → 110 → cap bei 100
        mock_claude_client.analyze.return_value = (
            '{"confidence_score": 75, "pros": ["Trend"], "cons": [], "validated": false, "summary": ""}'
        )
        data = {
            "symbol": "AAPL",
            "macro": {"trading_allowed": True, "approved": True, "macro_bias": "bullish", "event_risk": "low"},
            "trend": {"direction": "long", "structure_status": "HH/HL", "strength_score": 9, "long_allowed": True, "short_allowed": False},
            "volatility": {"volatility_ok": True, "market_phase": "normal", "atr_value": 1.0, "session": "london", "setup_allowed": True, "approved": True, "rsi": 55.0},
            "level": {"nearest_level": {"type": "swing_high", "price": 100.0}, "distance_pct": 0.1, "reaction_score": 8, "level_score": 80},
            "entry": {"entry_type": "breakout", "entry_price": 100.0, "trigger_condition": "close above", "candle_pattern": "engulfing", "entry_found": True, "confidence": 0.8},
            "risk": {"stop_loss": 99.0, "take_profit": 103.0, "crv": 3.0, "lot_size": 0.1, "trade_allowed": True},
        }
        result = agent.analyze(data)
        assert "mtf_confluence" in result
        assert "confluence_score" in result["mtf_confluence"]
        # Score sollte erhöht sein (triple_confluence)
        assert result["confidence_score"] > 75

    def test_mtf_confluence_in_analyze_output(self, mock_claude_client):
        """mtf_confluence Schlüssel muss im analyze()-Output vorhanden sein."""
        agent = ValidationAgent(claude_client=mock_claude_client)
        data = {
            "symbol": "AAPL",
            "macro": {"trading_allowed": True, "macro_bias": "bullish", "event_risk": "low"},
            "trend": {"direction": "long", "structure_status": "HH/HL", "strength_score": 7, "long_allowed": True, "short_allowed": False},
            "volatility": {"volatility_ok": True, "market_phase": "normal", "atr_value": 1.0, "session": "london", "setup_allowed": True, "rsi": 50.0},
            "level": {"nearest_level": None, "distance_pct": 0.5, "reaction_score": 5, "level_score": 50},
            "entry": {"entry_type": "pullback", "entry_price": 100.0, "trigger_condition": "", "candle_pattern": "", "entry_found": True, "confidence": 0.65},
            "risk": {"stop_loss": 99.0, "take_profit": 102.0, "crv": 3.0, "lot_size": 0.1, "trade_allowed": True},
        }
        result = agent.analyze(data)
        assert "mtf_confluence" in result
        mtf = result["mtf_confluence"]
        assert mtf["label"] in ("triple_confluence", "dual_confluence", "weak_confluence", "no_confluence")

    def test_no_confluence_reduces_score(self):
        """no_confluence modifier = 0.5 halbiert den Score (Multiplikation)."""
        agent = _make_agent()
        # Alle Kriterien schlecht → no_confluence
        results = {
            "trend": {"strength_score": 2},
            "level": {"level_score": 20},
            "entry": {"confidence": 0.1},
            "volatility": {"rsi": 80.0, "approved": False},
            "macro": {"trading_allowed": False},
        }
        mtf = agent._calculate_mtf_confluence(results)
        assert mtf["modifier"] < 1.0
