"""
ZoneExporter: Schreibt mt5_zones.json mit allen aktiven Forecast-Zonen und Signalen.

Format:
{
  "generated_at": "2026-03-27T09:00:00Z",
  "zones": [
    {
      "symbol": "EURUSD",
      "type": "forecast_zone",
      "direction": "long",
      "zone_high": 1.0860,
      "zone_low": 1.0830,
      "anchor_time": "2026-03-27T08:45:00Z",
      "color": "orange",
      "confidence": 65.0
    },
    {
      "symbol": "GBPUSD",
      "type": "signal_ready",
      "direction": "long",
      "entry_price": 1.2650,
      "stop_loss": 1.2610,
      "take_profit": 1.2730,
      "crv": 2.0,
      "confidence": 87.0,
      "trigger_hint": "Rejection-Wick bei 1.2650"
    }
  ]
}
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


class ZoneExporter:
    """
    Exportiert Forecast-Zonen, Signal-Ready und Active-Trades als JSON
    für den ZoneVisualizer MQL5 EA.
    """

    def __init__(self, config: Any) -> None:
        self.config = config

    def export(self, signals: list[dict], output_path: str | None = None) -> None:
        """
        Schreibt mt5_zones.json mit allen aktiven Zonen und Signalen.

        Args:
            signals: Liste von Signal-Dicts (aus model_dump oder aktiven Trades).
                     Nur Einträge mit gesetztem zone_status werden exportiert.
            output_path: Optionaler Override für den Zielpfad.
        """
        if not getattr(self.config, "mt5_zones_export_enabled", True):
            logger.debug("ZoneExporter: Export deaktiviert")
            return

        now_str = datetime.now(timezone.utc).isoformat()
        zones: list[dict] = []

        for s in signals:
            zone = self._signal_to_zone(s, now_str)
            if zone is not None:
                zones.append(zone)

        payload = {
            "generated_at": now_str,
            "zones": zones,
        }

        path = Path(output_path) if output_path else self._get_output_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(
                f"[ZoneExporter] {path} geschrieben "
                f"({len(zones)} Zone(n): "
                f"{sum(1 for z in zones if z['type'] == 'forecast_zone')} FZ | "
                f"{sum(1 for z in zones if z['type'] == 'signal_ready')} SIG | "
                f"{sum(1 for z in zones if z['type'] == 'active_trade')} AT)"
            )
        except OSError as e:
            logger.warning(f"[ZoneExporter] Schreiben fehlgeschlagen: {e}")

    # ── Private Hilfsmethoden ────────────────────────────────────────────────

    def _get_output_path(self) -> Path:
        """
        Gibt den Zielpfad für mt5_zones.json zurück.

        Priorität:
        1. mt5_zones_file wenn vollständiger Pfad → direkt verwenden
        2. mt5_common_files_path aus Config
        3. Windows-Auto-Erkennung via APPDATA
        4. Fallback: Output-Verzeichnis
        """
        zones_file = getattr(self.config, "mt5_zones_file", "mt5_zones.json")
        p = Path(zones_file)

        # Vollständiger Pfad → direkt verwenden
        if p.parent != Path("."):
            return p

        filename = p.name

        # Explizit konfigurierter Common-Files-Pfad
        common_path_str = getattr(self.config, "mt5_common_files_path", "") or ""
        if isinstance(common_path_str, str) and common_path_str:
            common = Path(common_path_str)
            common.mkdir(parents=True, exist_ok=True)
            return common / filename

        # Windows-Auto-Erkennung
        appdata = os.environ.get("APPDATA", "")
        if appdata and sys.platform == "win32":
            default = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
            default.mkdir(parents=True, exist_ok=True)
            return default / filename

        # Fallback: Output-Verzeichnis
        output = Path(getattr(self.config, "output_dir", "Output"))
        return output / filename

    def _signal_to_zone(self, s: dict, now_str: str) -> dict | None:
        """Konvertiert ein Signal-Dict in ein Zone-Dict für den Export."""
        zone_status = s.get("zone_status")
        if not zone_status:
            return None

        symbol = s.get("instrument", "")
        if not symbol:
            return None

        direction = str(s.get("direction", "")).split(".")[-1].lower()

        if zone_status == "forecast_zone":
            return self._build_forecast_zone(s, symbol, direction, now_str)
        if zone_status == "signal_ready":
            return self._build_signal_ready(s, symbol, direction)
        if zone_status == "active_trade":
            return self._build_active_trade(s, symbol, direction, now_str)
        return None

    def _build_forecast_zone(
        self, s: dict, symbol: str, direction: str, now_str: str
    ) -> dict:
        """Baut einen forecast_zone Eintrag."""
        agent_scores = s.get("agent_scores") or {}
        vol = agent_scores.get("volatility") or {}
        atr = float(vol.get("atr_value") or 0.0)

        zone_low = float(agent_scores.get("_zone_low") or 0.0)
        zone_high = float(agent_scores.get("_zone_high") or 0.0)

        # Fallback: nearest_level aus level-Ergebnis
        if zone_low == 0.0 or zone_high == 0.0:
            level = agent_scores.get("level") or {}
            nearest = level.get("nearest_level") or {}
            zone_price = float(nearest.get("price") or 0.0)
            zone_low = float(
                nearest.get("ob_low") or nearest.get("fvg_low") or (zone_price - atr * 0.5)
            )
            zone_high = float(
                nearest.get("ob_high") or nearest.get("fvg_high") or (zone_price + atr * 0.5)
            )

        return {
            "symbol": symbol,
            "type": "forecast_zone",
            "direction": direction,
            "zone_high": round(zone_high, 6),
            "zone_low": round(zone_low, 6),
            "anchor_time": now_str,
            "color": "orange",
            "confidence": float(s.get("confidence_score") or 0.0),
        }

    def _build_signal_ready(self, s: dict, symbol: str, direction: str) -> dict:
        """Baut einen signal_ready Eintrag."""
        return {
            "symbol": symbol,
            "type": "signal_ready",
            "direction": direction,
            "entry_price": float(s.get("entry_price") or 0.0),
            "stop_loss": float(s.get("stop_loss") or 0.0),
            "take_profit": float(s.get("take_profit") or 0.0),
            "crv": float(s.get("crv") or 0.0),
            "confidence": float(s.get("confidence_score") or 0.0),
            "trigger_hint": s.get("entry_trigger_hint") or "",
        }

    def _build_active_trade(
        self, s: dict, symbol: str, direction: str, now_str: str
    ) -> dict:
        """Baut einen active_trade Eintrag."""
        return {
            "symbol": symbol,
            "type": "active_trade",
            "direction": direction,
            "entry_price": float(s.get("entry_price") or 0.0),
            "stop_loss": float(s.get("stop_loss") or 0.0),
            "take_profit": float(s.get("take_profit") or 0.0),
            "open_time": str(s.get("timestamp") or now_str),
            "color": "blue",
            "mt5_ticket": s.get("mt5_ticket"),
        }
