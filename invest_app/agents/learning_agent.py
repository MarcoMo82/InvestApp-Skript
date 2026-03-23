"""
Learning-Agent: Post-Trade-Analyse und Muster-Erkennung.
Wertet geschlossene Trades aus, erkennt Muster bei Gewinnern/Verlierern
und generiert Parameter-Anpassungsempfehlungen.

Aufruf durch Orchestrator nach jedem Zyklus via run_post_cycle().
Kein LLM-Aufruf – rein regelbasierte statistische Analyse.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agents.base_agent import BaseAgent


class LearningAgent(BaseAgent):
    """
    Regelbasierter Lern-Agent für Post-Trade-Analyse.

    Liest geschlossene Trades aus der Datenbank, analysiert Muster in
    Gewinn- vs. Verlust-Trades und erzeugt Empfehlungen zur Optimierung
    von Konfidenz-Schwellenwert, ATR-Multiplikator und CRV.

    Input (analyze): {"recent_trades": list[dict]}
    Output: {
        "trades_analyzed": int,
        "insights": list[dict],
        "recommendations": list[dict],
        "log_path": Optional[str],
    }
    """

    MIN_SAMPLE_FOR_RECOMMENDATION = 5
    MIN_INSTRUMENT_SAMPLE = 3
    LOW_WIN_RATE_THRESHOLD = 50.0
    BAD_INSTRUMENT_THRESHOLD = 40.0
    HIGH_WIN_RATE_THRESHOLD = 65.0

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        db: Any = None,
        config: Any = None,
    ) -> None:
        super().__init__("learning_agent")
        self.output_dir = output_dir or Path("Output")
        self.db = db
        self._config = config

    def analyze(self, data: Any = None, **kwargs: Any) -> dict[str, Any]:
        """
        Analysiert Trades und erzeugt Muster-Erkenntnisse und Empfehlungen.

        Input data dict:
            recent_trades (list[dict]): Liste von Trade-Dicts mit Feldern
                instrument, direction, pnl, status, entry_price, sl, tp

        Output:
            trades_analyzed, insights, recommendations, log_path
        """
        if data is None:
            data = {}
        recent_trades: list[dict] = data.get("recent_trades", [])
        return self._process(recent_trades)

    def run_post_cycle(self, recent_trades: list[dict]) -> dict[str, Any]:
        """
        Wird vom Orchestrator am Ende jedes Zyklus aufgerufen.
        Kombiniert übergebene Trades mit historischen Trades aus der DB.

        Args:
            recent_trades: Frisch abgeschlossene Trades dieses Zyklus (kann leer sein)

        Returns:
            Ergebnis-dict mit insights, recommendations, trades_analyzed
        """
        all_trades = list(recent_trades) if recent_trades else []

        if self.db is not None:
            try:
                db_trades = self.db.get_closed_trades(days=30)
                existing_ids = {t.get("id") for t in all_trades if t.get("id")}
                for trade in db_trades:
                    if trade.get("id") not in existing_ids:
                        all_trades.append(trade)
            except Exception as e:
                self.logger.warning(f"DB-Abfrage fehlgeschlagen: {e}")

        result = self._process(all_trades)
        self.logger.info(
            f"[{self.name}] Post-Cycle abgeschlossen | "
            f"Trades: {result['trades_analyzed']} | "
            f"Erkenntnisse: {len(result['insights'])} | "
            f"Empfehlungen: {len(result['recommendations'])}"
        )
        return result

    # ------------------------------------------------------------------
    # Interne Analyse-Methoden
    # ------------------------------------------------------------------

    def _process(self, trades: list[dict]) -> dict[str, Any]:
        """Führt die vollständige Analyse durch und persistiert das Ergebnis."""
        closed = [
            t for t in trades
            if t.get("status") == "closed" and t.get("pnl") is not None
        ]

        if not closed:
            return {
                "agent": self.name,
                "success": True,
                "trades_analyzed": 0,
                "insights": [],
                "recommendations": [],
                "parameter_suggestions": [],
                "log_path": None,
            }

        insights = self._generate_insights(closed)
        recommendations = self._generate_recommendations(insights)
        trade_analysis = self._build_trade_analysis(closed, insights)
        parameter_suggestions = self._generate_parameter_suggestions(trade_analysis)
        log_path = self._persist(insights, recommendations, len(closed), parameter_suggestions)

        return {
            "agent": self.name,
            "success": True,
            "trades_analyzed": len(closed),
            "insights": insights,
            "recommendations": recommendations,
            "parameter_suggestions": parameter_suggestions,
            "log_path": log_path,
        }

    def _generate_insights(self, closed_trades: list[dict]) -> list[dict]:
        """Erzeugt statistische Erkenntnisse aus den abgeschlossenen Trades."""
        insights: list[dict] = []

        # Gesamt-Gewinnrate
        winners = [t for t in closed_trades if t.get("pnl", 0) > 0]
        overall_win_rate = round(len(winners) / len(closed_trades) * 100, 1)
        avg_pnl = round(
            sum(t.get("pnl", 0) for t in closed_trades) / len(closed_trades), 4
        )
        insights.append({
            "type": "overall_win_rate",
            "value": overall_win_rate,
            "sample_size": len(closed_trades),
            "avg_pnl": avg_pnl,
        })

        # Gewinnrate nach Instrument
        instruments = {t.get("instrument") for t in closed_trades if t.get("instrument")}
        for instrument in sorted(instruments):
            instr_trades = [t for t in closed_trades if t.get("instrument") == instrument]
            instr_wins = [t for t in instr_trades if t.get("pnl", 0) > 0]
            insights.append({
                "type": "win_rate_by_instrument",
                "instrument": instrument,
                "value": round(len(instr_wins) / len(instr_trades) * 100, 1),
                "sample_size": len(instr_trades),
                "avg_pnl": round(
                    sum(t.get("pnl", 0) for t in instr_trades) / len(instr_trades), 4
                ),
            })

        # Gewinnrate nach Richtung
        for direction in ("long", "short"):
            dir_trades = [t for t in closed_trades if t.get("direction") == direction]
            if dir_trades:
                dir_wins = [t for t in dir_trades if t.get("pnl", 0) > 0]
                insights.append({
                    "type": "win_rate_by_direction",
                    "direction": direction,
                    "value": round(len(dir_wins) / len(dir_trades) * 100, 1),
                    "sample_size": len(dir_trades),
                })

        # Durchschnittliches realisiertes CRV (tp_distance / sl_distance)
        crv_values = []
        for t in closed_trades:
            entry = t.get("entry_price")
            sl = t.get("sl")
            tp = t.get("tp")
            direction = t.get("direction")
            if entry and sl and tp and direction in ("long", "short"):
                if direction == "long":
                    sl_dist = abs(entry - sl)
                    tp_dist = abs(tp - entry)
                else:
                    sl_dist = abs(sl - entry)
                    tp_dist = abs(entry - tp)
                if sl_dist > 0:
                    crv_values.append(round(tp_dist / sl_dist, 2))

        if crv_values:
            insights.append({
                "type": "avg_planned_crv",
                "value": round(sum(crv_values) / len(crv_values), 2),
                "sample_size": len(crv_values),
            })

        return insights

    def _generate_recommendations(self, insights: list[dict]) -> list[dict]:
        """Leitet Parameter-Empfehlungen aus den Erkenntnissen ab."""
        recommendations: list[dict] = []

        overall = next(
            (i for i in insights if i["type"] == "overall_win_rate"), None
        )

        if overall and overall["sample_size"] >= self.MIN_SAMPLE_FOR_RECOMMENDATION:
            win_rate = overall["value"]

            if win_rate < self.LOW_WIN_RATE_THRESHOLD:
                recommendations.append({
                    "type": "increase_confidence_threshold",
                    "parameter": "min_confidence_score",
                    "action": "increase",
                    "current_win_rate": win_rate,
                    "suggestion": (
                        f"Gewinnrate {win_rate}% unter 50% – "
                        "Mindest-Confidence auf 85% erhöhen empfohlen."
                    ),
                })

            if win_rate > self.HIGH_WIN_RATE_THRESHOLD:
                recommendations.append({
                    "type": "review_crv",
                    "parameter": "min_crv",
                    "action": "increase",
                    "current_win_rate": win_rate,
                    "suggestion": (
                        f"Gewinnrate {win_rate}% hoch – "
                        "Mindest-CRV erhöhen, um mehr Gewinn pro Trade zu erzielen."
                    ),
                })

        # Schwache Instrumente identifizieren
        for insight in insights:
            if (
                insight["type"] == "win_rate_by_instrument"
                and insight["sample_size"] >= self.MIN_INSTRUMENT_SAMPLE
                and insight["value"] < self.BAD_INSTRUMENT_THRESHOLD
            ):
                recommendations.append({
                    "type": "avoid_instrument",
                    "parameter": "symbols",
                    "action": "exclude",
                    "instrument": insight["instrument"],
                    "win_rate": insight["value"],
                    "suggestion": (
                        f"Instrument {insight['instrument']} mit Gewinnrate "
                        f"{insight['value']}% – temporär ausschließen empfohlen."
                    ),
                })

        # Richtungs-Bias prüfen
        long_insight = next(
            (i for i in insights if i["type"] == "win_rate_by_direction" and i["direction"] == "long"),
            None,
        )
        short_insight = next(
            (i for i in insights if i["type"] == "win_rate_by_direction" and i["direction"] == "short"),
            None,
        )
        if long_insight and short_insight:
            diff = abs(long_insight["value"] - short_insight["value"])
            if diff > 20 and long_insight["sample_size"] >= 3 and short_insight["sample_size"] >= 3:
                weaker = "long" if long_insight["value"] < short_insight["value"] else "short"
                recommendations.append({
                    "type": "direction_bias",
                    "parameter": "direction_filter",
                    "action": "review",
                    "weaker_direction": weaker,
                    "suggestion": (
                        f"{weaker.capitalize()}-Trades deutlich schlechter – "
                        "Einstiegskriterien für diese Richtung verschärfen."
                    ),
                })

        return recommendations

    def _build_trade_analysis(self, closed_trades: list[dict], insights: list[dict]) -> dict:
        """Extrahiert aggregierte Metriken für die Parameter-Suggestion-Logik."""
        overall = next((i for i in insights if i["type"] == "overall_win_rate"), None)
        win_rate = (overall["value"] / 100.0) if overall else 0.5
        total_trades = len(closed_trades)

        # Durchschnittlicher Entry-Slippage (entry_price vs. actual fill price wenn vorhanden)
        slippages = []
        for t in closed_trades:
            ep = t.get("entry_price")
            fill = t.get("fill_price")
            if ep and fill and ep > 0:
                slippages.append(abs(fill - ep) / ep)
        avg_entry_slippage = sum(slippages) / len(slippages) if slippages else 0.0

        # Forex SL-Verstöße (entry_price < 100 und sl_distance > 80 Pips)
        forex_sl_violations = 0
        forex_sl_pips_list = []
        for t in closed_trades:
            ep = t.get("entry_price", 0)
            sl = t.get("sl")
            if ep and sl and ep < 100:
                sl_pips = abs(ep - sl) / 0.0001
                if sl_pips > 80:
                    forex_sl_violations += 1
                forex_sl_pips_list.append(sl_pips)
        avg_forex_sl_pips = (
            round(sum(forex_sl_pips_list) / len(forex_sl_pips_list), 1)
            if forex_sl_pips_list else 80
        )

        # Sideways-Filter-Rate: Trades mit strength_score <= 3 (wurden verworfen)
        sideways_count = sum(
            1 for t in closed_trades
            if t.get("agent_scores", {}).get("trend", {}).get("strength_score", 10) <= 3
        )
        sideways_filter_rate = sideways_count / total_trades if total_trades > 0 else 0.0

        return {
            "win_rate": win_rate,
            "total_trades": total_trades,
            "avg_entry_slippage_pct": avg_entry_slippage,
            "forex_sl_violations": forex_sl_violations,
            "avg_forex_sl_pips": avg_forex_sl_pips,
            "sideways_filter_rate": sideways_filter_rate,
        }

    def _generate_parameter_suggestions(self, trade_analysis: dict) -> list[dict]:
        """
        Generiert Optimierungsvorschläge für konfigurierbare Parameter
        basierend auf Trade-Analyse.
        """
        suggestions: list[dict] = []

        # Entry-Toleranz optimieren
        avg_entry_slippage = trade_analysis.get("avg_entry_slippage_pct", 0)
        if avg_entry_slippage > 0.002:  # > 0.2% durchschnittlicher Slippage
            suggestions.append({
                "parameter": "watch_agent.entry_tolerance",
                "current_value": 0.0015,
                "suggested_value": round(avg_entry_slippage * 1.2, 4),
                "reason": (
                    f"Durchschnittlicher Entry-Slippage {avg_entry_slippage:.3%} "
                    "überschreitet Toleranz"
                ),
            })

        # SL-Grenze für Forex
        forex_sl_violations = trade_analysis.get("forex_sl_violations", 0)
        if forex_sl_violations > 0:
            suggestions.append({
                "parameter": "risk_agent.forex_max_pips",
                "current_value": 80,
                "suggested_value": trade_analysis.get("avg_forex_sl_pips", 80),
                "reason": f"{forex_sl_violations} Trades durch SL-Grenze abgelehnt",
            })

        # ATR-Schwelle für Seitwärtsmarkt
        sideways_false_positives = trade_analysis.get("sideways_filter_rate", 0)
        if sideways_false_positives > 0.4:  # > 40% der Signale durch Sideways-Filter verworfen
            suggestions.append({
                "parameter": "trend_agent.sideways_atr_threshold",
                "current_value": 0.7,
                "suggested_value": round(0.7 * 0.8, 2),
                "reason": (
                    f"Sideways-Filter verwirft {sideways_false_positives:.0%} der Signale "
                    "— evtl. zu restriktiv"
                ),
            })

        # Confidence-Threshold
        win_rate = trade_analysis.get("win_rate", 0.5)
        if win_rate < 0.45 and trade_analysis.get("total_trades", 0) >= 10:
            suggestions.append({
                "parameter": "validation_agent.confidence_threshold",
                "current_value": 0.80,
                "suggested_value": 0.85,
                "reason": f"Win-Rate {win_rate:.0%} unter Ziel — Confidence-Schwelle erhöhen",
            })

        return suggestions

    def _persist(
        self,
        insights: list[dict],
        recommendations: list[dict],
        trade_count: int,
        parameter_suggestions: Optional[list[dict]] = None,
    ) -> Optional[str]:
        """Speichert Erkenntnisse als JSON-Logdatei im Output-Verzeichnis."""
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            log_path = self.output_dir / f"learning_{timestamp}.json"
            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "trades_analyzed": trade_count,
                "insights": insights,
                "recommendations": recommendations,
                "parameter_suggestions": parameter_suggestions or [],
            }
            log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            self.logger.debug(f"Learning-Log gespeichert: {log_path}")
            return str(log_path)
        except Exception as e:
            self.logger.warning(f"Persistierung fehlgeschlagen: {e}")
            return None
