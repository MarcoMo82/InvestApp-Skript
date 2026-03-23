"""
Abstrakte Basisklasse für alle Agenten der InvestApp Pipeline.
Definiert das einheitliche Interface und bietet Logging + Fehlerbehandlung.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from utils.logger import get_logger


class BaseAgent(ABC):
    """
    Abstrakte Basisklasse.
    Alle Agenten erben von dieser Klasse und implementieren analyze().
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.logger = get_logger(f"agents.{name}")
        self._last_result: Optional[dict] = None
        self._call_count: int = 0
        self._total_duration_ms: float = 0.0

    @abstractmethod
    def analyze(self, data: Any = None, **kwargs: Any) -> dict[str, Any]:
        """
        Führt die Analyse durch und gibt ein strukturiertes Ergebnis zurück.

        Args:
            data: Input-Daten für den Agenten (Symbol, OHLCV, vorherige Agent-Outputs, etc.)

        Returns:
            dict mit agent-spezifischen Ausgaben + Pflichtfeldern:
            - 'agent': Name des Agenten
            - 'success': bool
            - 'error': Optional[str]
        """
        ...

    def run(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Führt analyze() aus mit Zeitmessung und Fehlerbehandlung.
        Sollte statt analyze() direkt aufgerufen werden.

        Returns:
            Ergebnis-dict mit Metadaten (duration_ms, agent, success)
        """
        start = time.monotonic()
        symbol = data.get("symbol", data.get("instrument", "UNKNOWN"))
        self.logger.debug(f"[{self.name}] Starte Analyse für: {symbol}")

        try:
            result = self.analyze(data)
            result.setdefault("agent", self.name)
            result.setdefault("success", True)
            result.setdefault("error", None)

        except Exception as e:
            self.logger.error(f"[{self.name}] Fehler bei {symbol}: {e}", exc_info=True)
            result = {
                "agent": self.name,
                "success": False,
                "error": str(e),
            }

        duration_ms = (time.monotonic() - start) * 1000
        result["duration_ms"] = round(duration_ms, 1)

        self._last_result = result
        self._call_count += 1
        self._total_duration_ms += duration_ms

        self.logger.debug(
            f"[{self.name}] Analyse abgeschlossen | "
            f"Symbol: {symbol} | Dauer: {duration_ms:.0f}ms | "
            f"Erfolg: {result.get('success')}"
        )
        return result

    def stats(self) -> dict:
        """Gibt Laufzeit-Statistiken zurück."""
        avg_ms = (
            self._total_duration_ms / self._call_count if self._call_count > 0 else 0.0
        )
        return {
            "agent": self.name,
            "call_count": self._call_count,
            "avg_duration_ms": round(avg_ms, 1),
            "total_duration_ms": round(self._total_duration_ms, 1),
        }

    def _require_field(self, data: dict, field: str) -> Any:
        """Prüft ob ein Pflichtfeld vorhanden ist, wirft sonst ValueError."""
        if field not in data:
            raise ValueError(f"[{self.name}] Pflichtfeld fehlt: '{field}'")
        return data[field]
