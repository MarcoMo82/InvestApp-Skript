"""
Tages-Log als JSON: speichert Analyse-Zyklen, Order-Ereignisse und Trade-Ergebnisse.
Eine Datei pro Tag: cycle_log_YYYY-MM-DD.json im konfigurierten Verzeichnis.
Bestehende Dateien werden im Append-Modus erweitert.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CycleLogger:
    """
    Persistiert Analyse-Zyklen, Orders und Trade-Ergebnisse als JSON-Tagesdatei.

    Dateiname: cycle_log_YYYY-MM-DD.json
    Format:
    {
        "date": "2026-03-27",
        "cycles": [...],
        "orders": [...],
        "trade_results": [...]
    }

    Thread-sicher über Lock.
    """

    def __init__(self, config: Any = None) -> None:
        """
        Args:
            config: Config-Objekt. Liest 'cycle_log_dir' (Default: "logs/cycles")
                    und 'cycle_log_enabled' (Default: True).
        """
        self._config = config
        self._lock = threading.Lock()

        # Basis-Verzeichnis aus Config ermitteln
        log_dir_raw = getattr(config, "cycle_log_dir", None) if config is not None else None
        if log_dir_raw is None:
            log_dir_raw = "logs/cycles"

        # Relativen Pfad zur config.json-Position auflösen wenn möglich
        if isinstance(log_dir_raw, Path):
            self._log_dir = log_dir_raw
        else:
            # Versuche relativ zum config-Pfad aufzulösen
            config_parent: Optional[Path] = None
            try:
                if config is not None:
                    cfg_path = getattr(config, "_path", None)
                    if cfg_path is not None:
                        config_parent = Path(cfg_path).parent
            except Exception:
                pass

            if config_parent is not None:
                self._log_dir = config_parent / str(log_dir_raw)
            else:
                self._log_dir = Path(str(log_dir_raw))

        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._today: str = ""
        self._data: dict = {}
        self._file_path: Optional[Path] = None
        self._ensure_today()

    # ── Öffentliche Methoden ─────────────────────────────────────────────────

    def log_cycle(
        self,
        cycle_nr: int,
        timestamp: str,
        symbols_analyzed: list,
        results: list[dict],
    ) -> None:
        """Speichert einen vollständigen Analyse-Zyklus.

        Args:
            cycle_nr: Laufende Zyklus-Nummer
            timestamp: ISO-Zeitstempel des Zyklus (z.B. "2026-03-27T10:15:00Z")
            symbols_analyzed: Liste analysierter Symbole
            results: Liste von Ergebnis-Dicts (eines pro Symbol)
        """
        if not self._is_enabled():
            return

        entry = {
            "cycle_nr": cycle_nr,
            "timestamp": timestamp,
            "symbols_analyzed": list(symbols_analyzed),
            "results": list(results),
        }
        with self._lock:
            self._ensure_today()
            self._data["cycles"].append(entry)
            self._save()

    def log_order(
        self,
        event: str,
        symbol: str,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        crv: float,
        confidence: float,
        agent_params: dict,
    ) -> None:
        """Speichert ein Order-Ereignis.

        Args:
            event: "open" | "close" | "sl_hit" | "tp_hit"
            symbol: Symbol-Name (z.B. "EURUSD")
            direction: "long" | "short"
            entry: Entry-Preis
            sl: Stop-Loss-Preis
            tp: Take-Profit-Preis
            crv: Chance-Risiko-Verhältnis
            confidence: Confidence Score (0–100)
            agent_params: Agenten-Ergebnisse aus agent_scores
        """
        if not self._is_enabled():
            return

        order_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "sl": sl,
            "tp": tp,
            "crv": crv,
            "confidence": confidence,
            "agent_params": agent_params,
        }
        with self._lock:
            self._ensure_today()
            self._data["orders"].append(order_entry)
            self._save()

    def log_trade_result(
        self,
        symbol: str,
        direction: str,
        pnl_pips: float,
        outcome: str,
        agent_params: dict,
    ) -> None:
        """Speichert das Trade-Ergebnis für den Learning Agent.

        Args:
            symbol: Symbol-Name
            direction: "long" | "short"
            pnl_pips: Gewinn/Verlust in Pips
            outcome: "win" | "loss" | "breakeven"
            agent_params: Agenten-Ergebnisse aus agent_scores
        """
        if not self._is_enabled():
            return

        result_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "direction": direction,
            "pnl_pips": pnl_pips,
            "outcome": outcome,
            "agent_params": agent_params,
        }
        with self._lock:
            self._ensure_today()
            self._data["trade_results"].append(result_entry)
            self._save()

    # ── Interne Hilfsmethoden ────────────────────────────────────────────────

    def _is_enabled(self) -> bool:
        """Prüft ob Logging aktiviert ist."""
        if self._config is None:
            return True
        return bool(getattr(self._config, "cycle_log_enabled", True))

    def _ensure_today(self) -> None:
        """Stellt sicher dass _data für den aktuellen Tag geladen ist."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today == self._today:
            return

        self._today = today
        self._file_path = self._log_dir / f"cycle_log_{today}.json"

        if self._file_path.exists():
            try:
                raw = self._file_path.read_text(encoding="utf-8")
                self._data = json.loads(raw)
                # Fehlende Felder ergänzen (Vorwärtskompatibilität)
                self._data.setdefault("date", today)
                self._data.setdefault("cycles", [])
                self._data.setdefault("orders", [])
                self._data.setdefault("trade_results", [])
            except Exception as e:
                logger.warning(f"CycleLogger: Bestehende Datei beschädigt, neu erstellen: {e}")
                self._data = self._empty_day(today)
        else:
            self._data = self._empty_day(today)

    def _empty_day(self, date: str) -> dict:
        """Erstellt ein leeres Tages-Dict."""
        return {
            "date": date,
            "cycles": [],
            "orders": [],
            "trade_results": [],
        }

    def _save(self) -> None:
        """Schreibt _data atomisch als JSON in die Tagesdatei."""
        if self._file_path is None:
            return
        try:
            tmp = self._file_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self._file_path)
        except Exception as e:
            logger.error(f"CycleLogger: Fehler beim Schreiben: {e}")
