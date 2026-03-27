"""
Learning-Agent: Post-Trade-Analyse und Muster-Erkennung.
Wertet geschlossene Trades aus, erkennt Muster bei Gewinnern/Verlierern
und generiert Parameter-Anpassungsempfehlungen.

Aufruf durch Orchestrator nach jedem Zyklus via run_post_cycle().
Kein LLM-Aufruf – rein regelbasierte statistische Analyse.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
        order_db: Any = None,
        config_path: Optional[Path] = None,
    ) -> None:
        super().__init__("learning_agent")
        self.output_dir = output_dir or Path("Output")
        self.db = db
        self._config = config
        self.order_db = order_db          # OrderDB für Trade-Kontext (Post-Trade-Analyse)
        self._config_path = config_path   # Pfad zur config.json für Auto-Anpassung

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

    def analyze_from_logs(
        self,
        log_dir: str,
        lookback_days: int = 30,
    ) -> list[dict]:
        """Liest alle Tages-Logs der letzten N Tage und analysiert Muster.

        Analysiert:
        1. Trefferquote pro Entry-Typ (rejection_wick vs pullback vs breakout)
        2. Beste RSI-Range für erfolgreiche Trades
        3. Optimaler CRV-Bereich
        4. Welche Makro-Bias-Kombinationen am besten performen
        5. Häufigste Ablehnungsgründe für verworfene Symbole

        Args:
            log_dir: Verzeichnis mit cycle_log_YYYY-MM-DD.json Dateien
            lookback_days: Anzahl Tage zurück (Default: 30)

        Returns:
            Liste von Erkenntnissen mit 'type', 'finding', 'suggestion'
        """
        log_path = Path(log_dir)
        if not log_path.exists():
            self.logger.warning(f"analyze_from_logs: Verzeichnis nicht gefunden: {log_dir}")
            return []

        # Relevante Datumswerte bestimmen
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        log_files = sorted(log_path.glob("cycle_log_*.json"))

        all_trade_results: list[dict] = []
        all_cycles: list[dict] = []

        for f in log_files:
            # Datum aus Dateiname extrahieren
            try:
                date_str = f.stem.replace("cycle_log_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if file_date < cutoff:
                    continue
            except ValueError:
                continue

            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                all_trade_results.extend(data.get("trade_results", []))
                all_cycles.extend(data.get("cycles", []))
            except Exception as e:
                self.logger.warning(f"analyze_from_logs: Fehler beim Lesen von {f.name}: {e}")

        insights: list[dict] = []

        # Alle Ergebnisse aus cycle-Daten extrahieren
        all_results: list[dict] = []
        for cycle in all_cycles:
            for result in cycle.get("results", []):
                all_results.append(result)

        wins = [r for r in all_trade_results if r.get("outcome") == "win"]
        losses = [r for r in all_trade_results if r.get("outcome") == "loss"]

        # 1. Trefferquote pro Entry-Typ
        entry_type_stats: dict[str, list[bool]] = {}
        for cycle in all_cycles:
            for result in cycle.get("results", []):
                agents = result.get("agents") or {}
                entry_info = agents.get("entry") or {}
                entry_type = str(entry_info.get("type") or "").strip()
                if not entry_type:
                    continue
                zone_status = result.get("zone_status", "")
                # Nur abgeschlossene Signale (signal_ready zählt als ausgelöst)
                if zone_status == "signal_ready":
                    # Trade-Ergebnis aus trade_results suchen
                    symbol = result.get("symbol", "")
                    outcome = self._find_trade_outcome(all_trade_results, symbol)
                    if outcome is not None:
                        entry_type_stats.setdefault(entry_type, []).append(outcome)

        for entry_type, outcomes in entry_type_stats.items():
            if len(outcomes) >= 3:
                win_rate = sum(outcomes) / len(outcomes) * 100
                label = entry_type.replace("_", " ").title()
                insights.append({
                    "type": "entry_type_performance",
                    "finding": f"{label} hat {win_rate:.0f}% Trefferquote ({sum(outcomes)}/{len(outcomes)} Trades)",
                    "suggestion": f"entry_type_{entry_type}_weight {'erhöhen' if win_rate >= 60 else 'senken'}",
                })

        # 2. RSI-Range Analyse
        rsi_win: list[float] = []
        rsi_loss: list[float] = []
        for cycle in all_cycles:
            for result in cycle.get("results", []):
                agents = result.get("agents") or {}
                vol_info = agents.get("volatility") or {}
                rsi = vol_info.get("rsi")
                if rsi is None:
                    continue
                rsi = float(rsi)
                symbol = result.get("symbol", "")
                outcome = self._find_trade_outcome(all_trade_results, symbol)
                if outcome is True:
                    rsi_win.append(rsi)
                elif outcome is False:
                    rsi_loss.append(rsi)

        if len(rsi_win) >= 3 and len(rsi_loss) >= 3:
            avg_rsi_win = sum(rsi_win) / len(rsi_win)
            avg_rsi_loss = sum(rsi_loss) / len(rsi_loss)
            # Optimale Range bestimmen (±10 um Durchschnitt)
            rsi_low = max(0, round(avg_rsi_win - 10, 0))
            rsi_high = min(100, round(avg_rsi_win + 10, 0))
            insights.append({
                "type": "rsi_optimization",
                "finding": (
                    f"Trades mit RSI {rsi_low:.0f}-{rsi_high:.0f} haben "
                    f"{len(rsi_win)/(len(rsi_win)+len(rsi_loss))*100:.0f}% Trefferquote "
                    f"(Win-RSI Ø{avg_rsi_win:.1f} vs Loss-RSI Ø{avg_rsi_loss:.1f})"
                ),
                "suggestion": f"rsi_oversold_approach: Grenzwert auf {avg_rsi_win:.0f} anpassen",
            })

        # 3. Optimaler CRV-Bereich
        crv_win: list[float] = []
        crv_loss: list[float] = []
        for cycle in all_cycles:
            for result in cycle.get("results", []):
                agents = result.get("agents") or {}
                risk_info = agents.get("risk") or {}
                crv = risk_info.get("crv")
                if crv is None:
                    continue
                crv = float(crv)
                symbol = result.get("symbol", "")
                outcome = self._find_trade_outcome(all_trade_results, symbol)
                if outcome is True:
                    crv_win.append(crv)
                elif outcome is False:
                    crv_loss.append(crv)

        if len(crv_win) >= 3:
            avg_crv_win = sum(crv_win) / len(crv_win)
            insights.append({
                "type": "crv_optimization",
                "finding": (
                    f"Gewinn-Trades haben Ø CRV {avg_crv_win:.1f} "
                    f"(Basis: {len(crv_win)} Trades)"
                ),
                "suggestion": (
                    f"min_crv auf {max(2.0, round(avg_crv_win * 0.9, 1)):.1f} anpassen "
                    "(10% unter Win-Durchschnitt)"
                ),
            })

        # 4. Makro-Bias-Kombinationen
        bias_stats: dict[str, list[bool]] = {}
        for cycle in all_cycles:
            for result in cycle.get("results", []):
                agents = result.get("agents") or {}
                macro_info = agents.get("macro") or {}
                bias = str(macro_info.get("bias") or "").lower()
                direction = str(result.get("direction") or "").lower()
                if not bias or not direction:
                    continue
                combo = f"{bias}+{direction}"
                symbol = result.get("symbol", "")
                outcome = self._find_trade_outcome(all_trade_results, symbol)
                if outcome is not None:
                    bias_stats.setdefault(combo, []).append(outcome)

        best_combo = None
        best_rate = 0.0
        for combo, outcomes in bias_stats.items():
            if len(outcomes) >= 3:
                rate = sum(outcomes) / len(outcomes) * 100
                if rate > best_rate:
                    best_rate = rate
                    best_combo = combo

        if best_combo and best_rate > 0:
            bias_label, direction_label = best_combo.split("+", 1)
            insights.append({
                "type": "macro_bias_performance",
                "finding": (
                    f"Beste Kombination: Makro={bias_label.upper()} + {direction_label.upper()} "
                    f"mit {best_rate:.0f}% Trefferquote"
                ),
                "suggestion": f"Makro-Bias {bias_label.upper()} für {direction_label}-Trades priorisieren",
            })

        # 5. Häufigste Ablehnungsgründe
        rejection_counts: dict[str, int] = {}
        for result in all_results:
            if result.get("zone_status") == "rejected":
                agent = result.get("rejection_agent", "unbekannt")
                reason = result.get("rejection_reason", "")
                key = f"{agent}: {reason}" if reason else agent
                rejection_counts[key] = rejection_counts.get(key, 0) + 1

        if rejection_counts:
            top_reason, count = max(rejection_counts.items(), key=lambda x: x[1])
            total_rejected = len([r for r in all_results if r.get("zone_status") == "rejected"])
            pct = count / total_rejected * 100 if total_rejected > 0 else 0
            insights.append({
                "type": "rejection_analysis",
                "finding": (
                    f"Häufigster Ablehnungsgrund: '{top_reason}' "
                    f"({count}/{total_rejected} = {pct:.0f}% aller Ablehnungen)"
                ),
                "suggestion": f"Filter für '{top_reason}' überprüfen und ggf. lockern",
            })

        # Ergebnis ausgeben
        if insights:
            try:
                from utils.verbose_display import print_learning_summary
                print_learning_summary(insights, self._config)
            except Exception:
                pass

        return insights

    def _find_trade_outcome(
        self,
        trade_results: list[dict],
        symbol: str,
    ) -> Optional[bool]:
        """Sucht das letzte Trade-Ergebnis für ein Symbol.

        Returns:
            True = win, False = loss, None = nicht gefunden
        """
        for result in reversed(trade_results):
            if result.get("symbol") == symbol:
                outcome = result.get("outcome", "")
                if outcome == "win":
                    return True
                if outcome == "loss":
                    return False
                if outcome == "breakeven":
                    return None
        return None

    # ------------------------------------------------------------------
    # Post-Trade Mini-Analyse (wird pro Trade nach Schließung aufgerufen)
    # ------------------------------------------------------------------

    def analyze_closed_trade(self, ticket: int) -> dict:
        """
        Analysiert einen abgeschlossenen Trade und gibt Erkenntnisse zurück.
        Wird direkt nach Trade-Schließung vom Watch Agent aufgerufen.
        """
        if self.order_db is None:
            return {}
        trade = self.order_db.get_trade_context(ticket)
        if not trade:
            return {}

        insights: dict = {}

        # 1. War Confidence korrekt?
        confidence = trade.get("confidence") or 0
        won = (trade.get("pnl_pips") or trade.get("pnl") or 0) > 0
        insights["confidence_accurate"] = won == (confidence >= 80)

        # 2. ATR-Exkursion: Wieviel ATR lief der Trade in/gegen unsere Richtung?
        atr = trade.get("atr_value") or 1.0
        direction = (trade.get("trend_direction") or trade.get("direction") or "").upper()
        entry = float(trade.get("entry_price") or 0)

        if direction in ("LONG", "BUY"):
            max_excursion = ((trade.get("max_price_reached") or entry) - entry) / atr
            adverse_excursion = (entry - (trade.get("min_price_reached") or entry)) / atr
        else:
            max_excursion = (entry - (trade.get("min_price_reached") or entry)) / atr
            adverse_excursion = ((trade.get("max_price_reached") or entry) - entry) / atr

        insights["max_favorable_atr"] = round(max_excursion, 2)
        insights["max_adverse_atr"] = round(adverse_excursion, 2)
        insights["exit_reason"] = trade.get("exit_reason", "UNKNOWN")
        insights["symbol"] = trade.get("symbol")
        insights["won"] = won

        # 3. Pattern-Key für Aggregation
        pattern_key = (
            f"{trade.get('symbol')}_{trade.get('entry_type')}"
            f"_{trade.get('rsi_zone')}_{trade.get('volatility_phase')}"
        )
        insights["pattern_key"] = pattern_key

        # In DB als analysiert markieren
        try:
            self.order_db.mark_learning_analyzed(ticket, insights)
        except Exception as e:
            self.logger.warning(f"mark_learning_analyzed Fehler: {e}")

        self.logger.info(
            "[Learning] Trade %s analysiert | Won=%s | MaxFav=%.2f ATR | MaxAdv=%.2f ATR | Grund=%s",
            ticket, won, max_excursion, adverse_excursion, insights["exit_reason"],
        )
        return insights

    def check_and_apply_config_adjustments(self) -> list[dict]:
        """
        Prüft ob ein Verlust-Muster ≥ 10× vorkommt und passt config.json an.
        Liest alle unanalysierten Trades, sucht nach Mustern, erhöht Confidence-Schwelle.
        """
        if self.order_db is None:
            return []

        from collections import Counter

        try:
            unanalyzed = self.order_db.get_closed_unanalyzed_trades()
        except Exception as e:
            self.logger.warning(f"get_closed_unanalyzed_trades Fehler: {e}")
            return []

        # Verlust-Muster sammeln
        loss_patterns: list[str] = []
        for trade in unanalyzed:
            pnl = trade.get("pnl_pips") or trade.get("pnl") or 0
            if pnl < 0:
                key = (
                    f"{trade.get('symbol', '')}_{trade.get('entry_type', '')}"
                    f"_{trade.get('rsi_zone', '')}"
                )
                loss_patterns.append(key)

        pattern_counts = Counter(loss_patterns)
        adjustments_made: list[dict] = []

        cfg_threshold = (
            self._config.get("pipeline", {}).get("confidence_threshold", 80)
            if isinstance(self._config, dict)
            else getattr(self._config, "confidence_threshold", 80)
        )

        for pattern, count in pattern_counts.items():
            symbol = pattern.split("_")[0]
            if count < 10 or not symbol:
                continue

            # Symbol-spezifische Schwelle bestimmen
            sym_key = f"confidence_threshold_{symbol}"
            current_threshold = (
                self._config.get(sym_key, cfg_threshold)
                if isinstance(self._config, dict)
                else getattr(self._config, sym_key, cfg_threshold)
            )
            new_threshold = min(int(current_threshold) + 5, 95)

            if new_threshold > current_threshold:
                self._write_config_update(sym_key, new_threshold)
                entry = {
                    "pattern": pattern,
                    "occurrences": count,
                    "adjustment": f"{sym_key}: {current_threshold} → {new_threshold}",
                }
                adjustments_made.append(entry)
                self.logger.info("[Learning] Config angepasst: %s", entry)

        return adjustments_made

    def _write_config_update(self, key: str, value: Any) -> None:
        """Schreibt einen einzelnen Key in config.json (flach in pipeline-Sektion oder root)."""
        if self._config_path is None:
            return
        try:
            config_path = Path(self._config_path)
            if not config_path.exists():
                return
            raw = json.loads(config_path.read_text(encoding="utf-8"))

            # Versuche zuerst unter pipeline, dann root
            if "pipeline" in raw and key.startswith("confidence_threshold"):
                raw["pipeline"][key] = value
            else:
                raw[key] = value

            config_path.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.logger.info("[Learning] config.json aktualisiert: %s = %s", key, value)
        except Exception as e:
            self.logger.warning(f"_write_config_update Fehler: {e}")

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
