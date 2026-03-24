"""
Simulation-Agent: Erzeugt einmalige Test-Signale zur Pipeline-Validierung.
Aktiviert sich nach N Watch-Agent-Zyklen, injiziert ein synthetisches Signal
mit allen Agenten-Bedingungen als „grün" und deaktiviert sich nach Erfolg.
"""

from __future__ import annotations

import json
import logging
import pathlib
from datetime import datetime, timezone
from typing import Any, Optional


class SimulationAgent:
    """
    Erzeugt ein synthetisches Test-Signal das alle Agent-Bedingungen als positiv simuliert.
    Aktiviert sich nach N Watch-Agent-Zyklen und deaktiviert sich nach erfolgreicher Order.
    """

    def __init__(self, config: Any, connector: Any) -> None:
        self.config = config
        self.connector = connector
        self.watch_cycle_count: int = 0
        self.test_executed: bool = False
        self.logger = logging.getLogger(__name__)

    def on_watch_cycle(self) -> bool:
        """Wird nach jedem Watch-Agent-Lauf aufgerufen. Gibt True zurück wenn Test jetzt ausgelöst werden soll."""
        if not self.config.simulation_mode_enabled:
            return False
        if self.test_executed:
            return False
        self.watch_cycle_count += 1
        trigger = self.config.simulation_trigger_after_watch_cycles
        if self.watch_cycle_count >= trigger:
            self.logger.info(
                f"[Simulation] Test-Signal wird nach {trigger} Watch-Zyklen ausgelöst"
            )
            return True
        remaining = trigger - self.watch_cycle_count
        self.logger.info(
            f"[Simulation] Warte noch {remaining} Watch-Zyklen bis Test-Auslösung"
        )
        return False

    def generate_test_signal(self) -> dict:
        """Erzeugt ein synthetisches Signal mit allen Agenten auf 'grün'."""
        symbol = self.config.simulation_symbol
        direction = self.config.simulation_direction

        # Hole aktuellen Preis vom Connector
        try:
            price_info = self.connector.get_current_price(symbol)
            if isinstance(price_info, dict):
                current_price = float(price_info.get("last") or price_info.get("ask") or 1.0)
            else:
                current_price = float(price_info)
        except Exception:
            current_price = 1.0  # Fallback

        # Berechne realistische SL/TP (ATR-basiert: 20 Pips SL, 40 Pips TP → CRV 2:1)
        pip_size = 0.0001 if current_price < 100 else 1.0
        sl_distance = 20 * pip_size
        tp_distance = 40 * pip_size

        if direction == "long":
            stop_loss = round(current_price - sl_distance, 5)
            take_profit = round(current_price + tp_distance, 5)
        else:
            stop_loss = round(current_price + sl_distance, 5)
            take_profit = round(current_price - tp_distance, 5)

        return {
            "id": f"SIM-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "instrument": symbol,
            "direction": direction,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "lot_size": self.config.simulation_lot_size,
            "crv": 2.0,
            "confidence_score": 85.0,
            "status": "approved",
            "is_simulation": True,
            "entry_type": "market",
            "trend_status": "SIMULATION - above 200 EMA, strong trend",
            "macro_status": "SIMULATION - positive",
            "reasoning": "TEST-SIGNAL: Simulation aller Agent-Bedingungen als positiv",
            "pros": ["[SIMULATION] Alle Agenten grün", "[SIMULATION] Test-Modus aktiv"],
            "cons": ["[SIMULATION] Dies ist ein automatischer Test"],
            "agent_scores": {
                "trend_agent": {"direction": direction, "strength": "strong", "score": 85, "simulation": True},
                "volatility_agent": {"atr_ratio": 1.0, "rsi": 50, "score": 80, "simulation": True},
                "level_agent": {"level_score": 75, "simulation": True},
                "validation_agent": {"confidence": 85.0, "simulation": True, "success": True, "error": None},
            },
        }

    def mark_executed(self) -> None:
        """Markiert den Test als ausgeführt und deaktiviert den Test-Modus."""
        self.test_executed = True
        self.logger.info("[Simulation] ✅ Test-Order erfolgreich ausgelöst — Test-Modus deaktiviert")
        self.logger.info("[Simulation] Setze SIMULATION_MODE_ENABLED=False in Umgebung")
        result = {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "success": True,
            "message": "Test-Signal erfolgreich durch komplette Pipeline verarbeitet",
        }
        try:
            out_path = pathlib.Path("Output/simulation_result.json")
            out_path.parent.mkdir(exist_ok=True)
            out_path.write_text(json.dumps(result, indent=2))
        except Exception as e:
            self.logger.warning(f"[Simulation] Konnte Ergebnis nicht schreiben: {e}")
