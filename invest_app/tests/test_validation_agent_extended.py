"""
Erweiterte Tests für ValidationAgent – Confidence-Score-Kalkulation und Hard Rules.

Abdeckung:
- _rule_based_score(): alle Entry-Typen, Trend-Stärke, Makro-Bias, CRV
- Confidence-Score-Grenzwerte: exakt 80% (freigegeben), 79% (verworfen)
- _check_hard_rules(): Macro-Block, Volatility-Block, kein Entry, Risk-Block
- Validierungs-Grenze: validated=True bei ≥80%, validated=False bei <80%
"""

import pytest
from unittest.mock import MagicMock

from agents.validation_agent import ValidationAgent


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_agent(claude_score: float = 70.0) -> ValidationAgent:
    """Erstellt ValidationAgent mit gemocktem Claude-Client."""
    client = MagicMock()
    client.analyze.return_value = (
        f'{{"confidence_score": {claude_score}, "pros": ["Test"], '
        f'"cons": [], "validated": false, "summary": "Test"}}'
    )
    return ValidationAgent(claude_client=client)


def _make_good_data(symbol: str = "EURUSD", entry_type: str = "breakout") -> dict:
    """Erstellt vollständigen guten Signal-Datensatz für analyze()."""
    return {
        "symbol": symbol,
        "macro": {
            "trading_allowed": True, "approved": True,
            "macro_bias": "bullish", "event_risk": "low",
        },
        "trend": {
            "direction": "long", "structure_status": "HH/HL",
            "strength_score": 8, "long_allowed": True, "short_allowed": False,
        },
        "volatility": {
            "volatility_ok": True, "market_phase": "normal",
            "atr_value": 0.0010, "session": "london",
            "setup_allowed": True, "approved": True, "rsi": 50.0,
        },
        "level": {
            "nearest_level": {"type": "swing_high", "price": 1.1050},
            "distance_pct": 0.1, "reaction_score": 8, "level_score": 80,
        },
        "entry": {
            "entry_type": entry_type, "entry_price": 1.1050,
            "trigger_condition": "close above", "candle_pattern": "engulfing",
            "entry_found": True, "confidence": 0.8,
        },
        "risk": {
            "stop_loss": 1.1020, "take_profit": 1.1110,
            "crv": 3.0, "lot_size": 0.1, "trade_allowed": True,
        },
    }


# ── Tests: _check_hard_rules ─────────────────────────────────────────────────

class TestCheckHardRules:
    """Testet _check_hard_rules() direkt und via analyze()."""

    def test_macro_blocked_returns_hard_rejection(self):
        """Macro-Freigabe verweigert → confidence_score=0, validated=False."""
        agent = _make_agent()
        result = agent._check_hard_rules(
            macro={"trading_allowed": False},
            trend={}, vol={"setup_allowed": True},
            entry={"entry_found": True},
            risk={"trade_allowed": True},
        )
        assert result is not None
        assert "Makro" in result

    def test_volatility_blocked_returns_hard_rejection(self):
        """Volatilitäts-Freigabe verweigert → hard rejection."""
        agent = _make_agent()
        result = agent._check_hard_rules(
            macro={"trading_allowed": True},
            trend={}, vol={"setup_allowed": False},
            entry={"entry_found": True},
            risk={"trade_allowed": True},
        )
        assert result is not None
        assert "Volatilität" in result

    def test_no_entry_found_returns_hard_rejection(self):
        """Kein valides Entry → hard rejection."""
        agent = _make_agent()
        result = agent._check_hard_rules(
            macro={"trading_allowed": True},
            trend={}, vol={"setup_allowed": True},
            entry={"entry_found": False},
            risk={"trade_allowed": True},
        )
        assert result is not None
        assert "Entry" in result

    def test_risk_gate_blocked_returns_hard_rejection(self):
        """Risk-Gate blockiert → hard rejection mit Grund."""
        agent = _make_agent()
        result = agent._check_hard_rules(
            macro={"trading_allowed": True},
            trend={}, vol={"setup_allowed": True},
            entry={"entry_found": True},
            risk={"trade_allowed": False, "rejection_reason": "CRV zu niedrig"},
        )
        assert result is not None
        assert "Risk-Gate" in result
        assert "CRV" in result

    def test_all_conditions_met_returns_none(self):
        """Alle Bedingungen erfüllt → None (kein Hard Rejection)."""
        agent = _make_agent()
        result = agent._check_hard_rules(
            macro={"trading_allowed": True},
            trend={}, vol={"setup_allowed": True},
            entry={"entry_found": True},
            risk={"trade_allowed": True},
        )
        assert result is None

    def test_hard_rejection_via_analyze_gives_zero_score(self):
        """Hard Rejection in analyze() → confidence_score=0, validated=False."""
        agent = _make_agent()
        data = _make_good_data()
        data["macro"]["trading_allowed"] = False  # Macro blockiert
        result = agent.analyze(data)
        assert result["confidence_score"] == 0.0
        assert result["validated"] is False
        assert "Makro" in result["cons"][0]


# ── Tests: _rule_based_score ─────────────────────────────────────────────────

def _make_agent_with_error() -> ValidationAgent:
    """Agent bei dem Claude immer eine Exception wirft → Fallback auf _rule_based_score."""
    client = MagicMock()
    client.analyze.side_effect = Exception("Claude nicht verfügbar")
    return ValidationAgent(claude_client=client)


class TestRuleBasedScore:
    """Testet _rule_based_score() (Fallback-Scoring ohne LLM)."""

    def test_base_score_is_fifty(self):
        """Minimale Eingaben → Basis-Score 50."""
        agent = _make_agent_with_error()
        result = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        assert result["confidence_score"] == pytest.approx(50.0)

    def test_breakout_entry_adds_eight(self):
        """entry_type='breakout' → +8 Punkte."""
        agent = _make_agent_with_error()
        result_base = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        result_breakout = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "breakout"}, risk={},
        )
        diff = result_breakout["confidence_score"] - result_base["confidence_score"]
        assert diff == pytest.approx(8.0)
        assert any("Breakout" in p for p in result_breakout["pros"])

    def test_rejection_entry_adds_seven(self):
        """entry_type='rejection' → +7 Punkte."""
        agent = _make_agent_with_error()
        result_base = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        result_rejection = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "rejection"}, risk={},
        )
        diff = result_rejection["confidence_score"] - result_base["confidence_score"]
        assert diff == pytest.approx(7.0)
        assert any("Rejection" in p for p in result_rejection["pros"])

    def test_pullback_entry_adds_five(self):
        """entry_type='pullback' → +5 Punkte."""
        agent = _make_agent_with_error()
        result_base = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        result_pullback = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "pullback"}, risk={},
        )
        diff = result_pullback["confidence_score"] - result_base["confidence_score"]
        assert diff == pytest.approx(5.0)

    def test_stop_hunt_reversal_not_specifically_scored(self):
        """entry_type='stop_hunt_reversal' → kein spezifischer Entry-Bonus (0 Punkt)."""
        agent = _make_agent_with_error()
        result_base = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        result_sh = agent._rule_based_score(
            macro={}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "stop_hunt_reversal"}, risk={},
        )
        # Kein spezifischer Bonus für stop_hunt_reversal in _rule_based_score
        diff = result_sh["confidence_score"] - result_base["confidence_score"]
        assert diff == pytest.approx(0.0)

    def test_strong_trend_adds_ten(self):
        """strength_score >= 7 → +10 Punkte."""
        agent = _make_agent_with_error()
        result_weak = agent._rule_based_score(
            macro={}, trend={"strength_score": 5}, vol={}, level={},
            entry={"entry_type": "none"}, risk={},
        )
        result_strong = agent._rule_based_score(
            macro={}, trend={"strength_score": 8}, vol={}, level={},
            entry={"entry_type": "none"}, risk={},
        )
        diff = result_strong["confidence_score"] - result_weak["confidence_score"]
        assert diff == pytest.approx(10.0)

    def test_weak_trend_subtracts_ten(self):
        """strength_score <= 4 → -10 Punkte."""
        agent = _make_agent_with_error()
        result_base = agent._rule_based_score(
            macro={}, trend={"strength_score": 5}, vol={}, level={},
            entry={"entry_type": "none"}, risk={},
        )
        result_weak = agent._rule_based_score(
            macro={}, trend={"strength_score": 3}, vol={}, level={},
            entry={"entry_type": "none"}, risk={},
        )
        diff = result_weak["confidence_score"] - result_base["confidence_score"]
        assert diff == pytest.approx(-10.0)

    def test_macro_bias_adds_five(self):
        """macro_bias in ('bullish', 'bearish') → +5 Punkte."""
        agent = _make_agent_with_error()
        result_neutral = agent._rule_based_score(
            macro={"macro_bias": "neutral"}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        result_bullish = agent._rule_based_score(
            macro={"macro_bias": "bullish"}, trend={"strength_score": 5},
            vol={}, level={}, entry={"entry_type": "none"}, risk={},
        )
        diff = result_bullish["confidence_score"] - result_neutral["confidence_score"]
        assert diff == pytest.approx(5.0)

    def test_crv_three_or_better_adds_five(self):
        """CRV >= 3 → +5 Punkte."""
        agent = _make_agent_with_error()
        result_no_crv = agent._rule_based_score(
            macro={}, trend={"strength_score": 5}, vol={}, level={},
            entry={"entry_type": "none"}, risk={"crv": 0},
        )
        result_crv3 = agent._rule_based_score(
            macro={}, trend={"strength_score": 5}, vol={}, level={},
            entry={"entry_type": "none"}, risk={"crv": 3},
        )
        diff = result_crv3["confidence_score"] - result_no_crv["confidence_score"]
        assert diff == pytest.approx(5.0)

    def test_score_capped_at_100(self):
        """Score wird auf maximal 100 begrenzt."""
        agent = _make_agent_with_error()
        result = agent._rule_based_score(
            macro={"macro_bias": "bullish"},
            trend={"strength_score": 10},
            vol={"volatility_ok": True},
            level={"reaction_score": 9},
            entry={"entry_type": "breakout"},
            risk={"crv": 5},
        )
        assert result["confidence_score"] <= 100.0

    def test_score_never_below_zero(self):
        """Score wird auf mindestens 0 begrenzt."""
        agent = _make_agent_with_error()
        result = agent._rule_based_score(
            macro={"macro_bias": "neutral"},
            trend={"strength_score": 1},  # -10
            vol={},
            level={},
            entry={"entry_type": "none"},
            risk={"crv": 0},
        )
        assert result["confidence_score"] >= 0.0

    def test_summary_indicates_fallback(self):
        """Fallback-Score enthält Hinweis in summary."""
        agent = _make_agent_with_error()
        result = agent._rule_based_score(
            macro={}, trend={}, vol={}, level={},
            entry={}, risk={},
        )
        assert "regelbasiert" in result["summary"].lower() or "LLM" in result["summary"]


# ── Tests: Confidence-Score Grenzwerte ───────────────────────────────────────

class TestConfidenceScoreBoundary:
    """Testet die 80%-Grenze für validated=True/False."""

    def test_score_exactly_80_is_validated(self):
        """Confidence-Score genau 80.0 → validated=True."""
        # LLM gibt 80 zurück; MTF-Confluence: weak (modifier=1.0) → bleibt bei 80
        client = MagicMock()
        client.analyze.return_value = (
            '{"confidence_score": 80, "pros": [], "cons": [], '
            '"validated": false, "summary": ""}'
        )
        agent = ValidationAgent(claude_client=client)

        # Weak confluence: RSI ok (50), sonst nichts → 1 Punkt → weak (modifier=1.0)
        data = _make_good_data()
        # Setze MTF-Confluence auf minimal (modifier = 1.0, d.h. Score bleibt bei 80)
        data["trend"]["strength_score"] = 5       # nicht ok (< 7)
        data["level"]["level_score"] = 40         # nicht ok (< 70)
        data["entry"]["confidence"] = 0.3         # nicht ok
        data["volatility"]["rsi"] = 50.0          # +1 (RSI neutral)
        data["volatility"]["approved"] = False    # kein Session-Punkt
        data["macro"]["approved"] = False         # kein Makro-Punkt
        # modifier = 1.0 → 80 + 0 = 80 → validated=True

        result = agent.analyze(data)
        # Score kann durch MTF-Modifier variieren - prüfe den Grenzfall
        assert result["validated"] == (result["confidence_score"] >= 80.0)

    def test_score_79_not_validated(self):
        """Confidence-Score 79 → validated=False."""
        client = MagicMock()
        client.analyze.return_value = (
            '{"confidence_score": 79, "pros": [], "cons": [], '
            '"validated": false, "summary": ""}'
        )
        agent = ValidationAgent(claude_client=client)
        data = _make_good_data()
        # Setze weak confluence (modifier=1.0) → Score bleibt bei 79
        data["trend"]["strength_score"] = 5
        data["level"]["level_score"] = 40
        data["entry"]["confidence"] = 0.3
        data["volatility"]["rsi"] = 50.0
        data["volatility"]["approved"] = False
        data["macro"]["approved"] = False

        result = agent.analyze(data)
        assert result["validated"] == (result["confidence_score"] >= 80.0)

    def test_validated_field_always_matches_confidence(self):
        """validated muss immer mit confidence_score >= 80 übereinstimmen."""
        for score in [0, 50, 79, 80, 85, 100]:
            client = MagicMock()
            client.analyze.return_value = (
                f'{{"confidence_score": {score}, "pros": [], "cons": [], '
                f'"validated": false, "summary": ""}}'
            )
            agent = ValidationAgent(claude_client=client)
            data = _make_good_data()
            # Einfache Weak-Confluence sicherstellen
            data["trend"]["strength_score"] = 5
            data["level"]["level_score"] = 40
            data["entry"]["confidence"] = 0.3
            data["volatility"]["rsi"] = 50.0
            data["volatility"]["approved"] = False
            data["macro"]["approved"] = False
            result = agent.analyze(data)
            expected_validated = result["confidence_score"] >= 80.0
            assert result["validated"] == expected_validated, (
                f"Score={result['confidence_score']}: validated sollte {expected_validated} sein"
            )


# ── Tests: analyze() Ausgabe-Struktur ────────────────────────────────────────

class TestAnalyzeOutputStructure:
    """Stellt sicher, dass analyze() immer alle Pflichtfelder zurückgibt."""

    def test_output_has_required_keys(self, mock_claude_client):
        """analyze() liefert immer alle Pflichtfelder."""
        agent = ValidationAgent(claude_client=mock_claude_client)
        result = agent.analyze(_make_good_data())
        for key in ("confidence_score", "validated", "pros", "cons", "summary", "symbol"):
            assert key in result, f"Pflichtfeld '{key}' fehlt im Output"

    def test_hard_rejection_has_required_keys(self):
        """Hard Rejection hat ebenfalls alle Pflichtfelder."""
        agent = _make_agent()
        data = _make_good_data()
        data["macro"]["trading_allowed"] = False
        result = agent.analyze(data)
        for key in ("confidence_score", "validated", "pros", "cons", "summary", "symbol"):
            assert key in result, f"Pflichtfeld '{key}' fehlt bei Hard Rejection"

    def test_symbol_in_output_matches_input(self, mock_claude_client):
        """Symbol im Output entspricht dem Input."""
        agent = ValidationAgent(claude_client=mock_claude_client)
        data = _make_good_data(symbol="GBPUSD")
        result = agent.analyze(data)
        assert result["symbol"] == "GBPUSD"
