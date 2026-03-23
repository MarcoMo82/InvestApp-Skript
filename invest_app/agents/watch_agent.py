"""
Watch-Agent: Überwacht freigegebene Signale und führt Orders aus.
Ist der einzige Agent, der place_order() aufruft.
Prüft Entry-Bedingungen auf dem 1m-Chart bevor eine Order platziert wird.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)


class WatchAgent:
    """
    Verwaltet freigegebene Signale und prüft Entry-Bedingungen auf dem 1m-Chart.
    Ist der einzige Agent, der Orders platziert – verhindert doppelte Ausführung.
    """

    def __init__(
        self,
        connector: Any,
        db: Any = None,
        config: Any = None,
    ) -> None:
        self.connector = connector
        self.db = db
        self._config = config
        self._pending_signals: list[dict] = []
        self._lock = threading.Lock()

    def add_pending_signal(self, signal_dict: dict) -> None:
        """Fügt ein freigegebenes Signal zur Überwachungsliste hinzu."""
        with self._lock:
            self._pending_signals.append(signal_dict)
        logger.info(f"Signal zur Überwachung hinzugefügt: {signal_dict.get('instrument')}")

    def check_and_execute(self) -> list[dict]:
        """
        Prüft alle ausstehenden Signale auf Entry-Bedingungen.
        Führt Order aus wenn Bedingung erfüllt, behält restliche Signale.

        Returns:
            Liste der ausgeführten Signale
        """
        executed: list[dict] = []
        remaining: list[dict] = []

        with self._lock:
            signals = list(self._pending_signals)

        for signal in signals:
            instrument = signal.get("instrument", "UNKNOWN")
            try:
                ohlcv_1m = self.connector.get_ohlcv(instrument, "1m", 30)
                if ohlcv_1m is None or ohlcv_1m.empty:
                    remaining.append(signal)
                    continue

                if self._check_entry_condition(signal, ohlcv_1m):
                    self._place_order(signal)
                    executed.append(signal)
                    logger.info(f"Order ausgeführt: {instrument}")
                else:
                    remaining.append(signal)
            except Exception as e:
                logger.error(f"Fehler bei Signal-Prüfung {instrument}: {e}")
                remaining.append(signal)

        with self._lock:
            self._pending_signals = remaining

        return executed

    def _check_entry_condition(self, signal: dict, ohlcv_1m: pd.DataFrame) -> bool:
        """Prüft ob 1m-Chart die Entry-Bedingung für dieses Signal erfüllt."""
        entry_type = signal.get("entry_type", "market")
        current_price = float(ohlcv_1m["close"].iloc[-1])
        entry_price = signal.get("entry_price")
        direction = signal.get("direction")

        # EMA21 auf 1m-Chart
        ema21 = float(ohlcv_1m["close"].ewm(span=21).mean().iloc[-1])

        if entry_type == "pullback":
            # Warte bis Preis EMA21 berührt (± 0.05%)
            return abs(current_price - ema21) / ema21 < 0.0005

        elif entry_type == "breakout":
            # Warte auf Retest: Preis zurück zum Ausbruchslevel (entry_price ± 0.1%)
            if entry_price is None or entry_price == 0:
                return False
            return abs(current_price - entry_price) / entry_price < 0.001

        elif entry_type == "rejection":
            # Bestätigende Folgekerze: letzte Kerze muss in Signalrichtung schließen
            last_candle = ohlcv_1m.iloc[-1]
            if direction == "buy":
                return float(last_candle["close"]) > float(last_candle["open"])  # Bullische Kerze
            else:
                return float(last_candle["close"]) < float(last_candle["open"])  # Bearische Kerze

        else:  # "market" oder unbekannt
            # Sofort ausführen wenn Preis maximal 0.15% vom Entry entfernt
            if entry_price is None or entry_price == 0:
                return True  # Market-Order ohne Preisangabe: sofort ausführen
            return abs(current_price - entry_price) / entry_price < 0.0015

    def _place_order(self, signal: dict) -> dict:
        """Platziert eine Order über den Connector und speichert in der DB."""
        try:
            result: dict = {}
            if hasattr(self.connector, "place_order"):
                result = self.connector.place_order(signal) or {}
            if self.db is not None:
                self.db.save_trade(signal)
            return result
        except Exception as e:
            logger.error(f"Order-Platzierung fehlgeschlagen: {e}")
            return {}

    @property
    def pending_count(self) -> int:
        """Anzahl ausstehender Signale."""
        with self._lock:
            return len(self._pending_signals)
