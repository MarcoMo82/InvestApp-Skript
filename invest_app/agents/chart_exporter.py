"""
ChartExporter: Exportiert Analyse-Ergebnisse als JSON für MT5-Visualisierung.

Wird nach jeder Analyse aufgerufen und schreibt Output/mt5_zones.json,
die vom MQL5-Indikator InvestApp_Zones.mq5 eingelesen wird.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


class ChartExporter:
    """
    Schreibt nach jeder Analyse eine JSON-Datei für den MT5-Indikator.

    Die Datei enthält Zonen, Level, EMA-Referenzwerte und Signal-Status pro Symbol.
    Alle Pfade und Konfigurationswerte werden aus config gelesen.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self._data: dict[str, Any] = {}

    def export_zones(
        self,
        symbol: str,
        agent_results: dict[str, dict],
        signal: Optional[Any] = None,
    ) -> None:
        """
        Sammelt alle relevanten Daten aus den Agent-Ergebnissen und speichert sie intern.

        Args:
            symbol: Handelssymbol (z.B. "EURUSD")
            agent_results: Dict mit Agent-Outputs (keys: entry, risk, trend, level, ...)
            signal: Optional – fertiges Signal-Objekt (als Fallback für entry/sl/tp)
        """
        if not getattr(self.config, "mt5_zones_export_enabled", True):
            return

        entry_result = agent_results.get("entry", {})
        risk_result = agent_results.get("risk", {})
        trend_result = agent_results.get("trend", {})
        level_result = agent_results.get("level", {})

        # --- Entry-Zone ---
        entry_price = entry_result.get("entry_price") or (
            signal.entry_price if signal else None
        ) or 0.0
        entry_direction = entry_result.get("direction") or (
            signal.direction.value
            if signal and hasattr(signal.direction, "value")
            else "neutral"
        )
        entry_type = entry_result.get("entry_type", "unknown")
        tolerance_pct = getattr(self.config, "chart_entry_tolerance_pct", 0.05)

        entry_zone: Optional[dict] = None
        if entry_price:
            entry_zone = {
                "price": float(entry_price),
                "tolerance_pct": float(tolerance_pct),
                "direction": entry_direction,
                "type": entry_type,
            }

        # --- Stop Loss / Take Profit ---
        stop_loss = risk_result.get("stop_loss") or (
            signal.stop_loss if signal else 0.0
        ) or 0.0
        take_profit = risk_result.get("take_profit") or (
            signal.take_profit if signal else 0.0
        ) or 0.0

        # --- Order Blocks ---
        order_blocks_raw = level_result.get("order_blocks", [])
        order_blocks = order_blocks_raw if isinstance(order_blocks_raw, list) else []

        # --- Psychologische Level ---
        psych_raw = level_result.get("psychological_levels", [])
        psychological_levels = psych_raw if isinstance(psych_raw, list) else []

        # --- Key Levels (Support / Resistance) ---
        all_levels_raw = level_result.get("all_levels", [])
        key_levels: list[dict] = []
        if isinstance(all_levels_raw, list):
            for lvl in all_levels_raw:
                if isinstance(lvl, dict) and "price" in lvl:
                    key_levels.append(
                        {
                            "price": float(lvl.get("price", 0.0)),
                            "type": lvl.get("type", "support"),
                            "strength": int(lvl.get("strength", 1)),
                        }
                    )

        # --- EMA21 ---
        ema_values = trend_result.get("ema_values", {})
        ema21: Optional[float] = None
        if isinstance(ema_values, dict):
            ema21 = ema_values.get("ema_21")

        # --- Signal aktiv? ---
        signal_active = signal is not None

        self._data[symbol] = {
            "entry_zone": entry_zone,
            "stop_loss": float(stop_loss),
            "take_profit": float(take_profit),
            "order_blocks": order_blocks,
            "psychological_levels": psychological_levels,
            "key_levels": key_levels,
            "ema21": float(ema21) if ema21 is not None else None,
            "signal_active": signal_active,
        }

        logger.debug(f"ChartExporter: Zonen für {symbol} vorbereitet")

    def save(self) -> None:
        """
        Schreibt alle gesammelten Zonen als JSON in die konfigurierte Datei.
        Tut nichts wenn MT5_ZONES_EXPORT_ENABLED = False.
        """
        if not getattr(self.config, "mt5_zones_export_enabled", True):
            logger.debug("ChartExporter: Export deaktiviert – keine Datei geschrieben")
            return

        output_path = Path(
            getattr(self.config, "mt5_zones_file", "Output/mt5_zones.json")
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": self._data,
        }

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        logger.info(
            f"ChartExporter: JSON geschrieben → {output_path} "
            f"({len(self._data)} Symbol(e))"
        )

    def get_zones(self, symbol: str) -> dict:
        """Gibt die aktuellen Zonen für ein Symbol zurück."""
        return self._data.get(symbol, {})

    def get_all_symbols(self) -> list:
        """Gibt alle Symbole zurück für die Zonen vorhanden sind."""
        return list(self._data.keys())

    def update_zones(self, symbol: str, updates: dict) -> None:
        """
        Aktualisiert einzelne Felder einer Symbol-Zone ohne alles neu zu berechnen.
        updates kann enthalten: 'entry_zone', 'ema21', 'order_blocks', 'signal_active'
        """
        if symbol not in self._data:
            return

        zone = self._data[symbol]

        if "entry_zone" in updates:
            zone["entry_zone"] = updates["entry_zone"]

        if "ema21" in updates:
            zone["ema21"] = updates["ema21"]

        if "order_blocks" in updates:
            # Nur unconsumed OBs behalten
            zone["order_blocks"] = [
                ob for ob in updates["order_blocks"] if not ob.get("consumed", False)
            ]

        if "signal_active" in updates:
            zone["signal_active"] = updates["signal_active"]

        zone["last_watch_update"] = datetime.now(timezone.utc).isoformat()
        self._data[symbol] = zone

    def clear_symbol(self, symbol: str) -> None:
        """Entfernt ein Symbol aus den Daten (z.B. wenn kein Signal mehr aktiv ist)."""
        if symbol in self._data:
            del self._data[symbol]
            logger.debug(f"ChartExporter: {symbol} entfernt")
