"""
Reporting-Agent: Erstellt priorisierte Signallisten und Markdown-Reports.
Output: Signalliste + Report-Datei in Output/
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from models.signal import Signal, SignalStatus
from utils.terminal_display import print_signal_table
from utils.session import get_current_session


class ReportingAgent(BaseAgent):
    """
    Reporting-Agent für Signallisten und Markdown-Reports.
    Priorisiert Signale nach Confidence Score und speichert Reports in Output/.
    """

    def __init__(self, output_dir: Path) -> None:
        super().__init__("reporting_agent")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            signals (list[Signal]): Liste aller verarbeiteten Signale
            cycle_id (str, optional): Zyklus-ID für den Report

        Output:
            top_signals, report_path, signal_count
        """
        signals: list[Signal] = self._require_field(data, "signals")
        cycle_id = data.get("cycle_id", datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))

        # Signale ranken und filtern
        approved = [s for s in signals if s.status == SignalStatus.APPROVED]
        top_signals = sorted(approved, key=lambda s: s.confidence_score, reverse=True)

        # Report generieren
        report_content = self._generate_markdown_report(top_signals, cycle_id)
        report_path = self._save_report(report_content, cycle_id)

        self.logger.info(
            f"Report erstellt: {report_path} | "
            f"Signale gesamt: {len(signals)} | Freigegeben: {len(top_signals)}"
        )

        # Terminal-Ausgabe: Top-10-Tabelle
        macro_info: dict = {"cycle_id": cycle_id}
        if top_signals:
            agent_scores = top_signals[0].agent_scores or {}
            macro_data = agent_scores.get("macro") or {}
            if isinstance(macro_data, dict):
                macro_info["macro_bias"] = macro_data.get("macro_bias", "neutral")
            vol_data = agent_scores.get("volatility") or {}
            if isinstance(vol_data, dict):
                macro_info["volatility_ok"] = vol_data.get("setup_allowed", True)

        secondary = [
            s for s in signals
            if s.status.value != "approved" and s.confidence_score > 0
        ]
        try:
            session = get_current_session()
        except Exception:
            session = "N/A"

        print_signal_table(
            [s.model_dump(mode="json") for s in top_signals],
            macro_info=macro_info,
            session=session,
            secondary_signals=[s.model_dump(mode="json") for s in secondary],
        )

        return {
            "top_signals": [s.model_dump() for s in top_signals],
            "report_path": str(report_path),
            "signal_count": len(signals),
            "approved_count": len(top_signals),
            "cycle_id": cycle_id,
        }

    def _generate_markdown_report(self, signals: list[Signal], cycle_id: str) -> str:
        """Erstellt den Markdown-Report."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# InvestApp Signal-Report",
            f"**Zyklus:** {cycle_id}  ",
            f"**Erstellt:** {now}  ",
            f"**Freigegebene Signale:** {len(signals)}",
            "",
            "---",
            "",
        ]

        if not signals:
            lines.append("*Keine freigegeben Signale in diesem Zyklus.*")
            return "\n".join(lines)

        for i, signal in enumerate(signals, start=1):
            direction_icon = "🟢" if str(signal.direction) == "long" else "🔴"
            status_text = "✅ FREIGEGEBEN"

            lines.extend([
                f"## #{i} {direction_icon} {signal.instrument} – {str(signal.direction).upper()}",
                "",
                f"| Parameter | Wert |",
                f"|---|---|",
                f"| **Status** | {status_text} |",
                f"| **Confidence Score** | **{signal.confidence_score}%** |",
                f"| **Entry** | `{signal.entry_price:.5f}` |",
                f"| **Stop Loss** | `{signal.stop_loss:.5f}` |",
                f"| **Take Profit** | `{signal.take_profit:.5f}` |",
                f"| **CRV** | 1:{signal.crv} |",
                f"| **Lot-Größe** | {signal.lot_size} |",
                f"| **Trendstatus** | {signal.trend_status} |",
                f"| **Makrostatus** | {signal.macro_status} |",
                "",
                f"**Begründung:** {signal.reasoning}",
                "",
            ])

            if signal.pros:
                lines.append("**Argumente dafür:**")
                lines.extend(f"- ✓ {pro}" for pro in signal.pros)
                lines.append("")

            if signal.cons:
                lines.append("**Argumente dagegen:**")
                lines.extend(f"- ✗ {con}" for con in signal.cons)
                lines.append("")

            lines.append("---")
            lines.append("")

        # Zusammenfassung
        if signals:
            avg_score = sum(s.confidence_score for s in signals) / len(signals)
            best = signals[0]
            lines.extend([
                "## Zusammenfassung",
                "",
                f"- **Bestes Signal:** {best.instrument} {str(best.direction).upper()} ({best.confidence_score}%)",
                f"- **Durchschnittlicher Confidence Score:** {avg_score:.1f}%",
                f"- **Analysierte Signale:** {len(signals)}",
                "",
            ])

        return "\n".join(lines)

    def _save_report(self, content: str, cycle_id: str) -> Path:
        """Speichert den Report als Markdown-Datei."""
        filename = f"signal_report_{cycle_id}.md"
        path = self.output_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def generate_summary_line(self, signals: list[Signal]) -> str:
        """Gibt eine einzeilige Zusammenfassung der Top-Signale zurück."""
        approved = [s for s in signals if s.status == SignalStatus.APPROVED]
        if not approved:
            return "Keine freigegeben Signale."

        top = sorted(approved, key=lambda s: s.confidence_score, reverse=True)[:3]
        parts = [
            f"{s.instrument} {str(s.direction).upper()} ({s.confidence_score}%)"
            for s in top
        ]
        return " | ".join(parts)
