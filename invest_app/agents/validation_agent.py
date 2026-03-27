"""
Validation-Agent: LLM-gestützte Gesamtbewertung aller Agent-Outputs.
Output: confidence_score, pros, cons, validated
"""

from __future__ import annotations

import json
from typing import Any

from agents.base_agent import BaseAgent
from utils.claude_client import ClaudeClient

SYSTEM_PROMPT = """Du bist ein erfahrener Trading-Analyst der Trading-Signale kritisch bewertet.
Deine Aufgabe ist es, alle Agent-Outputs zu einer Gesamtbewertung zusammenzuführen.
Antworte NUR mit validem JSON."""

USER_PROMPT_TEMPLATE = """Bewerte folgendes Trading-Setup für {symbol}:

**Makro-Analyse:**
- Bias: {macro_bias}
- Event-Risiko: {event_risk}
- Trading erlaubt: {trading_allowed}

**Trend-Analyse:**
- Richtung: {direction}
- Struktur: {structure_status}
- Stärke: {strength_score}/10
- Long erlaubt: {long_allowed} | Short erlaubt: {short_allowed}

**Volatilität:**
- Volatilität ok: {volatility_ok}
- Marktphase: {market_phase}
- ATR: {atr_value}
- Session: {session}

**Level:**
- Nächstes Level: {nearest_level}
- Distanz: {distance_pct}%
- Reaktions-Score: {reaction_score}/10

**Entry:**
- Entry-Typ: {entry_type}
- Entry-Preis: {entry_price}
- Trigger: {trigger_condition}
- Candlestick: {candle_pattern}

**Risk:**
- SL: {stop_loss} | TP: {take_profit}
- CRV: 1:{crv}
- Lot-Größe: {lot_size}
- Trade erlaubt: {trade_allowed}

Vergib einen Confidence-Score von 0–100 basierend auf der Konsistenz aller Signale.
Pflichtregeln (Verstoß = Score < 60):
- Kein Trade gegen den Haupttrend
- Kein Signal ohne Volatilitätsfreigabe
- Kein Entry ohne bestätigte Level-Logik
- Kein Trade ohne sauberes Risiko-Setup

Antworte mit JSON:
{{
  "confidence_score": 0-100,
  "pros": ["Pro 1", "Pro 2", "Pro 3"],
  "cons": ["Contra 1", "Contra 2"],
  "validated": true/false,
  "summary": "Kurze Zusammenfassung in 2-3 Sätzen"
}}"""


class ValidationAgent(BaseAgent):
    """LLM-gestützter Validation-Agent für die finale Signal-Bewertung."""

    def __init__(self, claude_client: ClaudeClient) -> None:
        super().__init__("validation_agent")
        self.claude = claude_client

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            symbol (str): Symbol
            macro (dict): Makro-Agent Output
            trend (dict): Trend-Agent Output
            volatility (dict): Volatilitäts-Agent Output
            level (dict): Level-Agent Output
            entry (dict): Entry-Agent Output
            risk (dict): Risk-Agent Output

        Output:
            confidence_score, pros, cons, validated, summary
        """
        symbol = self._require_field(data, "symbol")
        macro = data.get("macro", {})
        trend = data.get("trend", {})
        vol = data.get("volatility", {})
        level = data.get("level", {})
        entry = data.get("entry", {})
        risk = data.get("risk", {})

        # Vorprüfung: Harte Ausschlüsse ohne LLM-Aufruf
        hard_rejection = self._check_hard_rules(macro, trend, vol, entry, risk)
        if hard_rejection:
            return {
                "symbol": symbol,
                "confidence_score": 0.0,
                "pros": [],
                "cons": [hard_rejection],
                "validated": False,
                "summary": f"Hartes Ausschlusskriterium: {hard_rejection}",
            }

        # LLM-Bewertung
        nearest = level.get("nearest_level") or {}
        prompt = USER_PROMPT_TEMPLATE.format(
            symbol=symbol,
            macro_bias=macro.get("macro_bias", "neutral"),
            event_risk=macro.get("event_risk", "medium"),
            trading_allowed=macro.get("trading_allowed", True),
            direction=trend.get("direction", "neutral"),
            structure_status=trend.get("structure_status", ""),
            strength_score=trend.get("strength_score", 5),
            long_allowed=trend.get("long_allowed", False),
            short_allowed=trend.get("short_allowed", False),
            volatility_ok=vol.get("volatility_ok", False),
            market_phase=vol.get("market_phase", "unknown"),
            atr_value=vol.get("atr_value", 0.0),
            session=vol.get("session", "unknown"),
            nearest_level=f"{nearest.get('type', 'n/a')} @ {nearest.get('price', 0.0):.5f}" if nearest else "keins",
            distance_pct=level.get("distance_pct", 0.0),
            reaction_score=level.get("reaction_score", 0),
            entry_type=entry.get("entry_type", "none"),
            entry_price=entry.get("entry_price", 0.0),
            trigger_condition=entry.get("trigger_condition", ""),
            candle_pattern=entry.get("candle_pattern", ""),
            stop_loss=risk.get("stop_loss", 0.0),
            take_profit=risk.get("take_profit", 0.0),
            crv=risk.get("crv", 0.0),
            lot_size=risk.get("lot_size", 0.0),
            trade_allowed=risk.get("trade_allowed", False),
        )

        try:
            response = self.claude.analyze(prompt, system_prompt=SYSTEM_PROMPT)
            result = self._parse_response(response)
        except Exception as e:
            self.logger.error(f"Claude-Aufruf fehlgeschlagen: {e}")
            # Fallback: regelbasierter Score
            result = self._rule_based_score(macro, trend, vol, level, entry, risk)

        # MTF-Konfluenz berechnen und auf Score anwenden
        mtf = self._calculate_mtf_confluence(
            {"macro": macro, "trend": trend, "volatility": vol, "level": level, "entry": entry}
        )
        base_score = result.get("confidence_score", 50.0)
        modifier = mtf.get("modifier", 1.0)
        if modifier < 1.0:
            modified_score = base_score * modifier
        else:
            modified_score = base_score + (modifier - 1.0) * 100
        result["confidence_score"] = min(100.0, max(0.0, modified_score))
        result["mtf_confluence"] = mtf

        result["symbol"] = symbol
        confidence_score = result.get("confidence_score", 0.0)
        result["validated"] = confidence_score >= 80.0
        return result

    def _check_hard_rules(
        self, macro: dict, trend: dict, vol: dict, entry: dict, risk: dict
    ) -> str | None:
        """Prüft harte Ausschlussregeln. Gibt Grund zurück oder None."""
        if not macro.get("trading_allowed", True):
            return "Makro-Freigabe verweigert (hohes Event-Risiko)"
        if not vol.get("setup_allowed", False):
            return "Volatilitäts-Freigabe verweigert"
        if not entry.get("entry_found", False):
            return "Kein valides Entry-Setup"
        if not risk.get("trade_allowed", True):
            return f"Risk-Gate: {risk.get('rejection_reason', 'unbekannt')}"
        return None

    def _parse_response(self, response: str) -> dict:
        """Parst die JSON-Antwort von Claude."""
        try:
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            parsed = json.loads(response)
            confidence_score = min(max(float(parsed.get("confidence_score", 50)), 0.0), 100.0)
            return {
                "confidence_score": confidence_score,
                "pros": parsed.get("pros", []),
                "cons": parsed.get("cons", []),
                "validated": False,  # Wird danach gesetzt
                "summary": parsed.get("summary", ""),
            }
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.warning(f"JSON-Parsing fehlgeschlagen: {e}")
            return {"confidence_score": 50.0, "pros": [], "cons": ["Parsing-Fehler"], "validated": False, "summary": ""}

    @staticmethod
    def _calculate_mtf_confluence(agent_results: dict) -> dict:
        """
        Berechnet den Multi-Timeframe-Konfluenz-Score aus allen Agent-Outputs.

        Score-Matrix:
          5–6 Punkte → triple_confluence  → +0.35
          3–4 Punkte → dual_confluence    → +0.15
          1–2 Punkte → weak_confluence    →  0.0
          0 Punkte   → no_confluence      → ×0.5 (modifier = -0.5)
        """
        score = 0
        details = []

        trend = agent_results.get("trend", {})
        if trend.get("trend_score", trend.get("strength_score", 0)) >= 7:
            score += 1
            details.append("EMA-Alignment stark")

        level = agent_results.get("level", {})
        if level.get("level_score", level.get("reaction_score", 0) * 10) >= 70:
            score += 1
            details.append("Preis an Key-Level")

        entry = agent_results.get("entry", {})
        if entry.get("confidence", 0) >= 0.6:
            score += 1
            details.append("Entry-Setup bestätigt")

        volatility = agent_results.get("volatility", {})
        rsi = volatility.get("rsi", 50)
        if 30 < rsi < 70:
            score += 1
            details.append("RSI neutral/konform")

        if volatility.get("approved", volatility.get("setup_allowed", False)):
            score += 1
            details.append("Session aktiv")

        macro = agent_results.get("macro", {})
        if macro.get("approved", macro.get("trading_allowed", False)):
            score += 1
            details.append("Makro-Bias kongruent")

        if score >= 5:
            modifier = 1.35
            label = "triple_confluence"
        elif score >= 3:
            modifier = 1.15
            label = "dual_confluence"
        elif score >= 1:
            modifier = 1.0
            label = "weak_confluence"
        else:
            modifier = 0.5
            label = "no_confluence"

        return {
            "confluence_score": score,
            "modifier": modifier,
            "label": label,
            "details": details,
        }

    def _rule_based_score(
        self, macro: dict, trend: dict, vol: dict, level: dict, entry: dict, risk: dict
    ) -> dict:
        """Fallback-Scoring ohne LLM."""
        score = 50.0
        pros = []
        cons = []

        if macro.get("macro_bias") in ("bullish", "bearish"):
            score += 5
            pros.append(f"Klarer Makro-Bias: {macro['macro_bias']}")

        strength = trend.get("strength_score", 5)
        if strength >= 7:
            score += 10
            pros.append(f"Starker Trend (Score: {strength}/10)")
        elif strength <= 4:
            score -= 10
            cons.append(f"Schwacher Trend (Score: {strength}/10)")

        if vol.get("volatility_ok"):
            score += 5
            pros.append("Volatilität im optimalen Bereich")

        if level.get("reaction_score", 0) >= 7:
            score += 10
            pros.append("Starkes Level mit hoher Reaktionswahrscheinlichkeit")

        entry_type = entry.get("entry_type", "none")
        if entry_type == "breakout":
            score += 8
            pros.append("Breakout-Setup bestätigt")
        elif entry_type == "rejection":
            score += 7
            pros.append("Rejection an Key-Level")
        elif entry_type == "pullback":
            score += 5
            pros.append("Pullback-Entry in Trendrichtung")

        crv = risk.get("crv", 0)
        if crv >= 3:
            score += 5
            pros.append(f"Hervorragendes CRV 1:{crv}")
        elif crv >= 2:
            score += 2
            pros.append(f"Akzeptables CRV 1:{crv}")

        return {
            "confidence_score": min(100.0, max(0.0, score)),
            "pros": pros,
            "cons": cons,
            "validated": False,
            "summary": "Regelbasierte Bewertung (LLM nicht verfügbar)",
        }
