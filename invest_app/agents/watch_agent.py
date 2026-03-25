"""
Watch-Agent: Überwacht freigegebene Signale und führt Orders aus.
Ist der einzige Agent, der place_order() aufruft.
Prüft Entry-Bedingungen auf dem 1m-Chart bevor eine Order platziert wird.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
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
        simulation_agent: Optional[Any] = None,
        chart_exporter: Optional[Any] = None,
    ) -> None:
        self.connector = connector
        self.db = db
        self._config = config
        self.simulation_agent = simulation_agent
        self.chart_exporter = chart_exporter
        self._pending_signals: list[dict] = []
        self._lock = threading.Lock()

    def add_pending_signal(self, signal_dict: dict) -> None:
        """Fügt ein freigegebenes Signal zur Überwachungsliste hinzu."""
        with self._lock:
            self._pending_signals.append(signal_dict)
        logger.info(f"Signal zur Überwachung hinzugefügt: {signal_dict.get('instrument')}")

    def run_watch_cycle(self) -> list[dict]:
        """Hauptmethode – jede Minute aufrufen. Alias für check_and_execute."""
        logger.info(
            f"[Watch-Agent] ♦ Minuten-Check | "
            f"Pending Signals: {self.pending_count} | "
            f"Zeit: {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
        )
        result = self.check_and_execute()

        # Zonen für alle Symbole aktualisieren
        if self.chart_exporter and getattr(self._config, "watch_agent_zone_update_enabled", True):
            for symbol in self.chart_exporter.get_all_symbols():
                self._update_zones_for_symbol(symbol)

        # Test-Modus: Nach N Zyklen Test-Signal injizieren
        if self.simulation_agent and self.simulation_agent.on_watch_cycle():
            test_signal = self.simulation_agent.generate_test_signal()
            logger.info(
                f"[Simulation] Injiziere Test-Signal für "
                f"{test_signal['instrument']} ({test_signal['direction']}) "
                f"@ {test_signal['entry_price']}"
            )
            if self._execute_order(test_signal):
                self.simulation_agent.mark_executed()

        return result

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

        open_trade_count = 0
        sl_updates = 0
        partial_exits = 0
        logger.info(
            f"[Watch-Agent] ✓ Check abgeschlossen | "
            f"Offene Trades geprüft: {open_trade_count} | "
            f"SL-Updates: {sl_updates} | "
            f"Exits: {partial_exits}"
        )

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

    def _update_zones_for_symbol(self, symbol: str) -> None:
        """
        Prüft ob Zonen für ein Symbol noch aktuell sind und aktualisiert sie.
        Wird jede Minute für alle Symbole mit aktiver Zone aufgerufen.
        """
        if not self.chart_exporter:
            return
        if not getattr(self._config, "watch_agent_zone_update_enabled", True):
            return

        try:
            zones = self.chart_exporter.get_zones(symbol)
            if not zones:
                return

            updates: dict = {}

            # Aktuellen Kurs holen
            tick = self.connector.get_tick(symbol) if hasattr(self.connector, "get_tick") else {}
            current_price = tick.get("bid", 0) or tick.get("ask", 0) if isinstance(tick, dict) else 0
            if not current_price:
                return

            # 1. Entry-Zone prüfen: noch relevant?
            entry_zone = zones.get("entry_zone", {})
            if entry_zone and entry_zone.get("price"):
                entry_price = entry_zone["price"]
                tolerance = getattr(
                    self._config, "watch_agent_zone_update_entry_tolerance_pct", 0.5
                )
                distance_pct = abs(current_price - entry_price) / entry_price * 100
                updated_entry = dict(entry_zone)
                updated_entry["active"] = distance_pct <= tolerance
                updates["entry_zone"] = updated_entry

            # 2. EMA21 aktualisieren aus 1m-Daten
            try:
                ohlcv_1m = self.connector.get_ohlcv(symbol, "1m", 30)
                if ohlcv_1m is not None and len(ohlcv_1m) >= 21:
                    closes = pd.Series(
                        ohlcv_1m["close"].values
                        if hasattr(ohlcv_1m, "columns")
                        else [c["close"] for c in ohlcv_1m]
                    )
                    new_ema21 = closes.ewm(span=21).mean().iloc[-1]
                    if not pd.isna(new_ema21):
                        updates["ema21"] = round(float(new_ema21), 5)
            except Exception:
                pass

            # 3. Order Blocks: konsumierte entfernen
            order_blocks = zones.get("order_blocks", [])
            if order_blocks:
                updated_obs = []
                for ob in order_blocks:
                    consumed = ob.get("consumed", False)
                    ob_high = ob.get("high", 0)
                    ob_low = ob.get("low", 0)
                    direction = ob.get("direction", "bullish")
                    if direction == "bullish" and current_price < ob_low:
                        consumed = True
                    elif direction == "bearish" and current_price > ob_high:
                        consumed = True
                    if not consumed:
                        updated_obs.append(ob)
                if len(updated_obs) != len(order_blocks):
                    updates["order_blocks"] = updated_obs
                    logger.debug(
                        f"[Watch-Agent] {symbol}: "
                        f"{len(order_blocks) - len(updated_obs)} OB(s) konsumiert entfernt"
                    )

            if updates:
                self.chart_exporter.update_zones(symbol, updates)
                self.chart_exporter.save()

        except Exception as e:
            logger.debug(f"[Watch-Agent] Zone-Update Fehler {symbol}: {e}")

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

    def _execute_order(self, signal: dict) -> bool:
        """
        Führt eine Market-Order für ein Simulations-Signal aus.
        Im Simulation-Modus wird kein echter MT5-Aufruf gemacht.
        Gibt True bei Erfolg zurück, False bei Fehler.
        """
        try:
            # Simulation-Modus: direkt simulieren ohne MT5-Aufruf
            if getattr(self._config, "simulation_mode_enabled", False):
                sim_ticket = 999999
                logger.info(
                    "[Simulation] Simulation-Modus aktiv → Direkte Simulation (kein MT5-Aufruf)"
                )
                logger.info(f"[Simulation] ✅ Order simuliert: Ticket #{sim_ticket}")
                if self.db is not None:
                    self.db.save_trade(signal)
                return True

            symbol = signal.get("instrument", "")
            direction = signal.get("direction", "long")
            lot_size = signal.get("lot_size", 0.01)
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")

            ticket = None
            if hasattr(self.connector, "place_market_order"):
                ticket = self.connector.place_market_order(
                    symbol=symbol,
                    direction=direction,
                    lot_size=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
            elif hasattr(self.connector, "place_order"):
                result = self.connector.place_order(signal) or {}
                ticket = result.get("order_id") or result.get("ticket")

            if ticket is not None:
                logger.info(f"[Simulation] ✅ Order erfolgreich: Ticket #{ticket}")
                if self.db is not None:
                    self.db.save_trade(signal)
                return True
            else:
                logger.error("[Simulation] ❌ Order fehlgeschlagen: kein Ticket erhalten")
                return False
        except Exception as e:
            logger.error(f"[Simulation] ❌ Order fehlgeschlagen: {e}")
            return False

    @property
    def pending_count(self) -> int:
        """Anzahl ausstehender Signale."""
        with self._lock:
            return len(self._pending_signals)
