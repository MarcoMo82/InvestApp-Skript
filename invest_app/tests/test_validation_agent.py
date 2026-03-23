"""Tests für den ValidationAgent – Confidence-Cap und Regelprüfung."""
from typing import Optional

import pytest
from unittest.mock import MagicMock

from agents.validation_agent import ValidationAgent


def _make_agent(llm_response: Optional[str] = None) -> ValidationAgent:
    client = MagicMock()
    if llm_response is not None:
        client.analyze.return_value = llm_response
    return ValidationAgent(claude_client=client)


def _full_input(symbol: str = "EURUSD", confidence: int = 85) -> dict:
    return {
        "symbol": symbol,
        "macro": {"macro_bias": "bullish", "event_risk": "low", "trading_allowed": True},
        "trend": {
            "direction": "long", "structure_status": "bullish structure intact",
            "strength_score": 8, "long_allowed": True, "short_allowed": False,
        },
        "volatility": {
            "volatility_ok": True, "market_phase": "normal",
            "atr_value": 0.0012, "session": "london", "setup_allowed": True,
        },
        "level": {"nearest_level": {"type": "support", "price": 1.0980}, "distance_pct": 0.1, "reaction_score": 8},
        "entry": {"entry_found": True, "entry_type": "pullback", "entry_price": 1.1000, "trigger_condition": "EMA touch", "candle_pattern": ""},
        "risk": {"stop_loss": 1.0950, "take_profit": 1.1100, "crv": 3.0, "lot_size": 0.1, "trade_allowed": True},
    }


class TestConfidenceCap:
    def test_llm_score_above_100_capped_to_100(self):
        """LLM gibt Score > 100 zurück → wird auf 100.0 gekappt."""
        resp = '{"confidence_score": 150, "pros": [], "cons": [], "validated": true, "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["confidence_score"] <= 100.0

    def test_llm_score_below_0_capped_to_0(self):
        """LLM gibt Score < 0 zurück → wird auf 0.0 gekappt."""
        resp = '{"confidence_score": -20, "pros": [], "cons": [], "validated": false, "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["confidence_score"] >= 0.0

    def test_normal_score_unchanged(self):
        """Normaler Score 85 bleibt unverändert."""
        resp = '{"confidence_score": 85, "pros": ["gut"], "cons": [], "validated": true, "summary": "ok"}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["confidence_score"] == pytest.approx(85.0)

    def test_score_100_not_capped(self):
        """Score = 100 bleibt bei 100."""
        resp = '{"confidence_score": 100, "pros": [], "cons": [], "validated": true, "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["confidence_score"] == pytest.approx(100.0)

    def test_score_0_not_capped(self):
        """Score = 0 bleibt bei 0."""
        resp = '{"confidence_score": 0, "pros": [], "cons": [], "validated": false, "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["confidence_score"] == pytest.approx(0.0)


class TestHardRules:
    def test_macro_blocked_returns_zero_score(self):
        """Makro-Freigabe verweigert → confidence_score = 0, validated = False."""
        agent = _make_agent()
        data = _full_input()
        data["macro"]["trading_allowed"] = False
        result = agent.analyze(data)
        assert result["confidence_score"] == 0.0
        assert result["validated"] is False

    def test_volatility_blocked_returns_zero_score(self):
        """Volatilitäts-Freigabe verweigert → confidence_score = 0."""
        agent = _make_agent()
        data = _full_input()
        data["volatility"]["setup_allowed"] = False
        result = agent.analyze(data)
        assert result["confidence_score"] == 0.0
        assert result["validated"] is False

    def test_no_entry_returns_zero_score(self):
        """Kein Entry-Setup → confidence_score = 0."""
        agent = _make_agent()
        data = _full_input()
        data["entry"]["entry_found"] = False
        result = agent.analyze(data)
        assert result["confidence_score"] == 0.0

    def test_risk_gate_rejected_returns_zero_score(self):
        """Risk-Gate abgelehnt → confidence_score = 0."""
        agent = _make_agent()
        data = _full_input()
        data["risk"]["trade_allowed"] = False
        data["risk"]["rejection_reason"] = "CRV zu niedrig"
        result = agent.analyze(data)
        assert result["confidence_score"] == 0.0


class TestValidatedFlag:
    def test_score_above_80_sets_validated_true(self):
        """Score ≥ 80 → validated = True."""
        resp = '{"confidence_score": 82, "pros": [], "cons": [], "validated": true, "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["validated"] is True

    def test_score_below_80_sets_validated_false(self):
        """Score < 80 → validated = False."""
        resp = '{"confidence_score": 70, "pros": [], "cons": [], "validated": false, "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input())
        assert result["validated"] is False

    def test_output_contains_symbol(self):
        """Result enthält symbol-Feld."""
        resp = '{"confidence_score": 85, "pros": [], "cons": [], "summary": ""}'
        agent = _make_agent(llm_response=resp)
        result = agent.analyze(_full_input(symbol="GBPUSD"))
        assert result["symbol"] == "GBPUSD"


class TestFallbackRuleBasedScore:
    def test_fallback_used_on_claude_error(self):
        """Bei Claude-Fehler wird regelbasierter Score verwendet, kein Absturz."""
        client = MagicMock()
        client.analyze.side_effect = RuntimeError("API down")
        agent = ValidationAgent(claude_client=client)
        result = agent.analyze(_full_input())
        assert "confidence_score" in result
        assert 0.0 <= result["confidence_score"] <= 100.0
        assert result["validated"] in (True, False)
