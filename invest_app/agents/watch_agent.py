"""
Watch-Agent: Überwacht freigegebene Signale und führt Orders aus.
Ist der einzige Agent, der place_order() aufruft.
Prüft Entry-Bedingungen auf dem 1m-Chart bevor eine Order platziert wird.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_ORDERS_PER_SYMBOL = 2  # Fallback wenn Config fehlt
_PENDING_FILE_TICKET = -1  # Sentinel: Order via pending_order.json geschrieben, kein MT5-Ticket


def _safe_float(val: Any) -> Optional[float]:
    """Konvertiert beliebige Typen sicher zu float oder None."""
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


class WatchAgent:
    """
    Verwaltet freigegebene Signale und prüft Entry-Bedingungen auf dem 1m-Chart.
    Ist der einzige Agent, der Orders platziert – verhindert doppelte Ausführung.
    """

    def __init__(
        self,
        connector: Any,
        trade_connector: Optional[Any] = None,
        db: Any = None,
        config: Any = None,
        simulation_agent: Optional[Any] = None,
        chart_exporter: Optional[Any] = None,
        risk_agent: Optional[Any] = None,
        order_db: Optional[Any] = None,
        cycle_logger: Optional[Any] = None,
        learning_agent: Optional[Any] = None,
    ) -> None:
        self.connector = connector
        self.trade_connector = trade_connector  # MT5Connector für Order-Execution (kein yfinance)
        self.db = db
        self._config = config
        self.simulation_agent = simulation_agent
        self.chart_exporter = chart_exporter
        self.risk_agent = risk_agent
        self.order_db = order_db          # OrderDB-Instanz für persistentes Tracking
        self.cycle_logger = cycle_logger  # Wird vom Orchestrator gesetzt
        self._learning_agent = learning_agent  # Learning Agent für Post-Trade-Analyse
        self._pending_signals: list[dict] = []
        self._lock = threading.Lock()
        self._last_sync_ts: float = 0.0   # Letzter MT5-Sync Timestamp
        self._sync_counter: int = 0        # Zähler für 15s-Ticks (Sync alle 4 Ticks = 60s)

    def add_pending_signal(self, signal_dict: dict) -> None:
        """Fügt ein freigegebenes Signal zur Überwachungsliste hinzu."""
        if "_signal_id" not in signal_dict:
            signal_dict["_signal_id"] = str(uuid.uuid4())
        with self._lock:
            self._pending_signals.append(signal_dict)
        logger.info(f"Signal zur Überwachung hinzugefügt: {signal_dict.get('instrument')}")

    def run_watch_cycle(self) -> list[dict]:
        """Hauptmethode – wird periodisch durch den Scheduler aufgerufen."""
        self._sync_counter += 1
        heartbeat_interval = getattr(self._config, "watch_agent_heartbeat_interval", 5) if self._config else 5
        do_full_sync = (self._sync_counter % heartbeat_interval == 0)

        result = self.check_and_execute()

        # MT5-Positionen nur alle N Zyklen synchronisieren
        if do_full_sync:
            self.sync_positions_from_mt5()

        # Status nur alle N Zyklen in Konsole ausgeben
        if do_full_sync:
            from utils.terminal_display import print_watch_update
            with self._lock:
                pending_snapshot = list(self._pending_signals)
            # Statistik aus OrderDB ableiten wenn verfügbar
            stats: dict = {
                "watched_symbols": len({s.get("instrument", "") for s in pending_snapshot}),
                "trades_today": 0,
                "pnl_today": 0.0,
            }
            if self.order_db is not None:
                try:
                    all_orders = self.order_db.get_all_orders() if hasattr(self.order_db, "get_all_orders") else []
                    today = datetime.now(timezone.utc).date().isoformat()
                    today_orders = [o for o in all_orders if str(o.get("created_at", "")).startswith(today)]
                    stats["trades_today"] = len(today_orders)
                    pnl = sum(float(o.get("pnl") or 0.0) for o in today_orders if o.get("pnl") is not None)
                    stats["pnl_today"] = pnl
                except Exception:
                    pass
            print_watch_update(pending_snapshot, stats)

        # Log nur bei Aktivität oder alle N Zyklen
        if result or do_full_sync:
            logger.info(
                f"[Watch-Agent] ♦ 15s-Check | "
                f"Pending: {self.pending_count} | "
                f"Ausgeführt: {len(result)} | "
                f"Zeit: {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
            )

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
        discarded: list[dict] = []
        watch_statuses: list[dict] = []

        with self._lock:
            signals = list(self._pending_signals)

        for signal in signals:
            instrument = signal.get("instrument", "UNKNOWN")
            try:
                ohlcv_1m = self.connector.get_ohlcv(instrument, "1m", 30)
                if ohlcv_1m is None or ohlcv_1m.empty:
                    logger.warning(f"[Watch] {instrument} | Keine 1m-Kursdaten → Signal bleibt ausstehend")
                    watch_statuses.append({
                        "instrument": instrument,
                        "entry_type": signal.get("entry_type", "market"),
                        "current_price": 0.0,
                        "entry_price": float(signal.get("entry_price") or 0.0),
                        "check_status": "warte",
                        "block_reason": "keine Kursdaten",
                    })
                    continue  # bleibt in _pending_signals

                current_price = float(ohlcv_1m["close"].iloc[-1])

                if self._check_entry_condition(signal, ohlcv_1m):
                    ticket = self._place_order(signal)
                    if ticket is not None and ticket != _PENDING_FILE_TICKET:
                        executed.append(signal)
                        check_status = "erfüllt"
                        logger.info(f"Order ausgeführt: {instrument}")
                    elif ticket == _PENDING_FILE_TICKET:
                        # Order via pending_order.json gequeued – kein Retry
                        executed.append(signal)
                        check_status = "datei"
                        logger.info(f"[Watch] {instrument} | Order via pending_order.json gequeued")
                    elif self.trade_connector is None:
                        # Reconnect fehlgeschlagen → nächster Zyklus versucht erneut
                        check_status = "kein MT5"
                        logger.warning(
                            f"[Watch] {instrument} | Entry-Bedingung erfüllt, "
                            f"aber MT5 nicht erreichbar → Signal bleibt in Überwachung"
                        )
                    else:
                        attempt = signal.get("_retry_count", 0) + 1
                        signal["_retry_count"] = attempt
                        logger.error(f"Order fehlgeschlagen, Retry {attempt}/3: {instrument}")
                        if attempt >= 3:
                            logger.error(f"Order nach 3 Versuchen verworfen: {instrument}")
                            discarded.append(signal)
                        check_status = "blockiert"
                        # else: bleibt in _pending_signals für nächsten Versuch
                else:
                    check_status = "warte"
                    # Bedingung nicht erfüllt → bleibt in _pending_signals

                watch_statuses.append({
                    "instrument": instrument,
                    "entry_type": signal.get("entry_type", "market"),
                    "current_price": current_price,
                    "entry_price": float(signal.get("entry_price") or 0.0),
                    "check_status": check_status,
                })

            except Exception as e:
                logger.error(f"Fehler bei Signal-Prüfung {instrument}: {e}")
                # bleibt in _pending_signals

        # Verbose: Watch-Check-Status pro Signal im Terminal anzeigen
        if watch_statuses:
            try:
                from utils.verbose_display import print_watch_entry_check
                print_watch_entry_check(watch_statuses, self._config)
            except Exception:
                pass

        with self._lock:
            # Nur ausgeführte und endgültig verworfene Signale entfernen.
            # Neu hinzugefügte Signale (während der Verarbeitung) bleiben erhalten.
            done_ids = {s.get("_signal_id") for s in executed + discarded}
            self._pending_signals = [
                s for s in self._pending_signals
                if s.get("_signal_id") not in done_ids
            ]

        open_trade_count = 0
        sl_updates = 0
        partial_exits = 0

        # Positions-Überwachung: Breakeven + Trailing Stop
        if self.db is not None and self.risk_agent is not None:
            try:
                open_trades = self.db.get_open_trades() if hasattr(self.db, "get_open_trades") else []
                open_trade_count = len(open_trades)
                for trade in open_trades:
                    ticket = trade.get("mt5_ticket")
                    symbol = trade.get("instrument") or trade.get("symbol")
                    direction = trade.get("direction", "")
                    entry_price = float(trade.get("entry_price", 0.0))
                    current_sl = float(trade.get("sl", 0.0))
                    take_profit = float(trade.get("tp", 0.0))

                    if not ticket or not symbol or direction not in ("long", "short") or entry_price <= 0:
                        continue

                    # Aktuellen Preis holen
                    tick = self.connector.get_tick(symbol) if hasattr(self.connector, "get_tick") else {}
                    if isinstance(tick, dict):
                        current_price = tick.get("bid", 0.0) if direction == "long" else tick.get("ask", 0.0)
                    else:
                        current_price = 0.0
                    if not current_price:
                        continue

                    # ATR und EMA21 aus 5m-OHLCV berechnen
                    atr = 0.0
                    ema21 = None
                    try:
                        ohlcv = self.connector.get_ohlcv(symbol, "5m", 20)
                        if ohlcv is not None and not ohlcv.empty and len(ohlcv) >= 14:
                            highs = ohlcv["high"]
                            lows = ohlcv["low"]
                            closes = ohlcv["close"]
                            tr = pd.concat([
                                highs - lows,
                                (highs - closes.shift(1)).abs(),
                                (lows - closes.shift(1)).abs(),
                            ], axis=1).max(axis=1)
                            atr = float(tr.rolling(14).mean().iloc[-1])
                            if len(ohlcv) >= 21:
                                ema21 = float(closes.ewm(span=21).mean().iloc[-1])
                    except Exception as e:
                        logger.warning(f"ATR/EMA-Berechnung fehlgeschlagen: {e}")
                        continue

                    if atr <= 0:
                        continue

                    sl_distance = abs(entry_price - current_sl)

                    # Breakeven prüfen (vor Trailing Stop)
                    if direction == "long":
                        one_to_one = entry_price + sl_distance
                        if current_price >= one_to_one and current_sl < entry_price:
                            if hasattr(self.connector, "modify_position"):
                                if self.connector.modify_position(ticket, entry_price):
                                    current_sl = entry_price
                                    sl_updates += 1
                                    logger.info(
                                        f"[Watch-Agent] Breakeven gesetzt: "
                                        f"Ticket {ticket} SL → {entry_price:.5f}"
                                    )
                    elif direction == "short":
                        one_to_one = entry_price - sl_distance
                        if current_price <= one_to_one and current_sl > entry_price:
                            if hasattr(self.connector, "modify_position"):
                                if self.connector.modify_position(ticket, entry_price):
                                    current_sl = entry_price
                                    sl_updates += 1
                                    logger.info(
                                        f"[Watch-Agent] Breakeven gesetzt: "
                                        f"Ticket {ticket} SL → {entry_price:.5f}"
                                    )

                    # Trailing Stop berechnen
                    new_sl = self.risk_agent.calculate_trailing_stop(
                        current_price=current_price,
                        current_sl=current_sl,
                        entry_price=entry_price,
                        take_profit=take_profit,
                        atr=atr,
                        direction=direction,
                        ema21=ema21,
                    )

                    # SL nur setzen wenn verbessert
                    improved = (direction == "long" and new_sl > current_sl) or \
                               (direction == "short" and new_sl < current_sl)
                    if improved and hasattr(self.connector, "modify_position"):
                        if self.connector.modify_position(ticket, new_sl):
                            sl_updates += 1
                            logger.info(
                                f"[Watch-Agent] Trailing Stop aktualisiert: "
                                f"Ticket {ticket} SL {current_sl:.5f} → {new_sl:.5f}"
                            )
            except Exception as e:
                logger.error(f"[Watch-Agent] Positions-Monitoring Fehler: {e}")

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
        instrument = signal.get("instrument", "UNKNOWN")

        # EMA21 auf 1m-Chart
        ema21 = float(ohlcv_1m["close"].ewm(span=21).mean().iloc[-1])

        if entry_type == "pullback":
            # Warte bis Preis EMA21 berührt (± 0.05%)
            distance_pct = abs(current_price - ema21) / ema21
            max_pct = 0.0005
            result = distance_pct < max_pct
            status = "✓ ERFÜLLT" if result else "✗ NICHT ERFÜLLT (zu weit von EMA)"
            logger.info(
                f"[Watch] {instrument} | Entry-Check: pullback | "
                f"Aktuell={current_price:.5f} | EMA21={ema21:.5f} | "
                f"Abstand={distance_pct * 100:.3f}% | Max={max_pct * 100:.2f}% → {status}"
            )
            return result

        elif entry_type == "breakout":
            # Warte auf Retest: Preis zurück zum Ausbruchslevel (entry_price ± 0.1%)
            if entry_price is None or entry_price == 0:
                logger.info(
                    f"[Watch] {instrument} | Entry-Check: breakout | "
                    f"Kein entry_price angegeben → ✗ NICHT ERFÜLLT"
                )
                return False
            distance_pct = abs(current_price - entry_price) / entry_price
            max_pct = 0.001
            result = distance_pct < max_pct
            status = "✓ ERFÜLLT" if result else "✗ NICHT ERFÜLLT (zu weit vom Ausbruchslevel)"
            logger.info(
                f"[Watch] {instrument} | Entry-Check: breakout | "
                f"Aktuell={current_price:.5f} | Entry={entry_price:.5f} | "
                f"Abstand={distance_pct * 100:.3f}% | Max={max_pct * 100:.2f}% → {status}"
            )
            return result

        elif entry_type == "rejection":
            # Bestätigende Folgekerze: letzte Kerze muss in Signalrichtung schließen
            last_candle = ohlcv_1m.iloc[-1]
            candle_open = float(last_candle["open"])
            candle_close = float(last_candle["close"])
            if direction == "long":
                result = candle_close > candle_open
                candle_dir = "bullisch" if candle_close > candle_open else "bearisch"
                status = "✓ ERFÜLLT" if result else "✗ NICHT ERFÜLLT (bearische Kerze, benötige bullische)"
            else:
                result = candle_close < candle_open
                candle_dir = "bearisch" if candle_close < candle_open else "bullisch"
                status = "✓ ERFÜLLT" if result else "✗ NICHT ERFÜLLT (bullische Kerze, benötige bearische)"
            logger.info(
                f"[Watch] {instrument} | Entry-Check: rejection | "
                f"Richtung={direction} | Kerze={candle_dir} "
                f"(O={candle_open:.5f} C={candle_close:.5f}) → {status}"
            )
            return result

        else:  # "market" oder unbekannt
            # Sofort ausführen wenn Preis maximal 0.15% vom Entry entfernt
            if entry_price is None or entry_price == 0:
                logger.info(
                    f"[Watch] {instrument} | Entry-Check: market | "
                    f"Kein entry_price → sofortige Ausführung → ✓ ERFÜLLT"
                )
                return True
            distance_pct = abs(current_price - entry_price) / entry_price
            max_pct = 0.0015
            result = distance_pct < max_pct
            status = "✓ ERFÜLLT" if result else "✗ NICHT ERFÜLLT (Preis zu weit vom Entry)"
            logger.info(
                f"[Watch] {instrument} | Entry-Check: market | "
                f"Aktuell={current_price:.5f} | Entry={entry_price:.5f} | "
                f"Abstand={distance_pct * 100:.3f}% | Max={max_pct * 100:.2f}% → {status}"
            )
            return result

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
            ob_consumed_threshold = getattr(
                self._config, "watch_agent_zone_update_ob_consumed_threshold", 0.3
            ) if self._config else 0.3
            order_blocks = zones.get("order_blocks", [])
            if order_blocks:
                updated_obs = []
                for ob in order_blocks:
                    consumed = ob.get("consumed", False)
                    ob_high = ob.get("high", 0)
                    ob_low = ob.get("low", 0)
                    ob_range = ob_high - ob_low
                    direction = ob.get("direction", "bullish")
                    if direction == "bullish":
                        # Konsumiert wenn Preis tiefer als (ob_low - threshold * ob_range)
                        threshold_price = ob_low - ob_consumed_threshold * ob_range if ob_range > 0 else ob_low
                        if current_price < threshold_price:
                            consumed = True
                    elif direction == "bearish":
                        # Konsumiert wenn Preis höher als (ob_high + threshold * ob_range)
                        threshold_price = ob_high + ob_consumed_threshold * ob_range if ob_range > 0 else ob_high
                        if current_price > threshold_price:
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

    def _try_reconnect_mt5(self) -> bool:
        """
        Versucht MT5Connector neu zu initialisieren (Lazy Reconnect, einmalig pro Aufruf).
        Bei Erfolg: self.trade_connector wird gesetzt und True zurückgegeben.
        """
        try:
            from data.mt5_connector import MT5_AVAILABLE, MT5Connector
            if not MT5_AVAILABLE:
                return False
            config = self._config
            if config is None or not getattr(config, "mt5_login", None):
                return False
            connector = MT5Connector(
                login=config.mt5_login,
                password=config.mt5_password,
                server=config.mt5_server,
                path=getattr(config, "mt5_path", ""),
                config=config,
            )
            if connector.connect():
                self.trade_connector = connector
                logger.info("[Watch] MT5 Lazy Reconnect erfolgreich – Trade-Connector aktiv.")
                return True
            logger.warning("[Watch] MT5 Lazy Reconnect fehlgeschlagen.")
            return False
        except Exception as e:
            logger.warning(f"[Watch] MT5 Lazy Reconnect Fehler: {e}")
            return False

    def _place_order(self, signal: dict) -> Optional[int]:
        """Platziert eine Market-Order über den Connector und speichert in der DB.

        Prüft vor der Ausführung:
        - Max. 2 Orders pro Symbol (MAX_ORDERS_PER_SYMBOL)
        - 2. Order nur wenn Confidence > bisherige Confidence

        Returns:
            Ticket-Nummer bei Erfolg, None bei Fehler oder Ablehnung.
        """
        try:
            symbol = signal.get("instrument", "")
            direction = signal.get("direction", "long")
            lot_size = signal.get("lot_size", 0.01)
            stop_loss = signal.get("stop_loss")
            take_profit = signal.get("take_profit")
            confidence = float(signal.get("confidence_score", signal.get("confidence", 0)))

            # ── Symbol-Limit prüfen ─────────────────────────────────────────
            max_orders = (
                getattr(self._config, "max_orders_per_symbol", _DEFAULT_MAX_ORDERS_PER_SYMBOL)
                if self._config is not None
                else _DEFAULT_MAX_ORDERS_PER_SYMBOL
            )
            if self.order_db is not None:
                count = self.order_db.get_order_count(symbol)
                if count >= max_orders:
                    logger.warning(
                        f"[Watch] {symbol} | Order-Guard: max_orders={max_orders}, aktuell={count} "
                        f"→ ✗ BLOCKIERT (Max-Orders erreicht)"
                    )
                    return None

                if count == 1:
                    max_conf = self.order_db.get_max_confidence(symbol)
                    if confidence <= max_conf:
                        logger.warning(
                            f"[Watch] {symbol} | Order-Guard: confidence={confidence:.0f}% ≤ "
                            f"bestehend={max_conf:.0f}% → ✗ BLOCKIERT (niedrigere Confidence)"
                        )
                        return None
                    logger.info(
                        f"[Watch] {symbol} | Order-Guard: confidence={confidence:.0f}% > "
                        f"bestehend={max_conf:.0f}% → ✓ 2. Order erlaubt"
                    )

            # ── Order-ID (UUID) generieren und in DB anlegen (status=pending) ─
            order_id = str(uuid.uuid4())
            signal_id = signal.get("id")
            if self.order_db is not None:
                self.order_db.add_order(
                    id=order_id,
                    symbol=symbol,
                    direction=direction,
                    sl=stop_loss or 0.0,
                    tp=take_profit or 0.0,
                    confidence=confidence,
                    lot_size=lot_size,
                    crv=float(signal.get("crv") or 0.0),
                    signal_id=signal_id,
                    entry_type=signal.get("entry_type"),
                    atr_value=_safe_float(signal.get("atr") or signal.get("atr_value")),
                    atr_pct=_safe_float(signal.get("atr_pct")),
                    rsi_value=_safe_float(signal.get("rsi_value")),
                    rsi_zone=signal.get("rsi_zone"),
                    volatility_phase=signal.get("volatility_phase"),
                    macro_bias=signal.get("macro_bias"),
                    trend_direction=signal.get("trend_direction") or direction,
                )

            # ── Order senden (nur über MT5Connector) ────────────────────────
            _trade_conn = self.trade_connector
            if _trade_conn is None:
                logger.warning("[Watch] Kein trade_connector – versuche MT5 neu zu verbinden...")
                if self._try_reconnect_mt5():
                    _trade_conn = self.trade_connector
                else:
                    logger.warning("[Watch] %s | MT5 nicht erreichbar – schreibe pending_order.json direkt", symbol)
                    ticket = self._write_pending_order_direct(
                        symbol, direction, lot_size, signal.get("entry_price"), stop_loss, take_profit,
                        signal=signal,
                    )
                    if ticket is not None:
                        return ticket
                    logger.error("[Watch] %s | Auch direkter Datei-Fallback fehlgeschlagen", symbol)
                    if self.order_db is not None:
                        self.order_db.mark_failed(order_id)
                    return None

            ticket = _trade_conn.place_market_order(
                symbol=symbol,
                direction=direction,
                lot_size=lot_size,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

            # ── Ergebnis in DB speichern ────────────────────────────────────
            if ticket is not None:
                if self.order_db is not None:
                    self.order_db.set_mt5_ticket(order_id, ticket)
                # invest_app.db: Archivierung erfolgt erst beim Close (in sync_positions_from_mt5)
                logger.info(
                    f"[Watch] {symbol} | Order erstellt: UUID={order_id} | MT5-Ticket={ticket}"
                )

                # Verbose: Order-Ereignis ausgeben
                try:
                    from utils.verbose_display import print_order_event
                    print_order_event("open", symbol, {
                        "direction": direction,
                        "entry_price": signal.get("entry_price", 0.0),
                        "sl": stop_loss or 0.0,
                        "tp": take_profit or 0.0,
                        "crv": signal.get("crv", 0.0),
                        "ticket": ticket,
                    }, self._config)
                except Exception:
                    pass

                # Tages-Log: Order persistieren
                if self.cycle_logger is not None:
                    try:
                        self.cycle_logger.log_order(
                            event="open",
                            symbol=symbol,
                            direction=str(direction),
                            entry=float(signal.get("entry_price") or 0.0),
                            sl=float(stop_loss or 0.0),
                            tp=float(take_profit or 0.0),
                            crv=float(signal.get("crv") or 0.0),
                            confidence=confidence,
                            agent_params=signal.get("agent_scores") or {},
                        )
                    except Exception as e:
                        logger.warning(f"CycleLogger log_order Fehler: {e}")

                return ticket
            else:
                # Fallback: pending_order.json sofort schreiben wenn MT5Connector (kein Retry)
                try:
                    from data.mt5_connector import MT5Connector as _MT5Connector
                    _is_mt5 = isinstance(_trade_conn, _MT5Connector)
                except Exception:
                    _is_mt5 = False
                if _is_mt5 and hasattr(_trade_conn, "write_order_file"):
                    signal_dict = {
                        "symbol": symbol,
                        "direction": "buy" if direction == "long" else "sell",
                        "volume": float(lot_size),
                        "sl": stop_loss,
                        "tp": take_profit,
                    }
                    _trade_conn.write_order_file(signal_dict)
                    logger.info(
                        f"[Watch] {symbol} | Fallback: pending_order.json geschrieben – kein Retry"
                    )
                    if self.order_db is not None:
                        self.order_db.mark_failed(order_id)
                    return _PENDING_FILE_TICKET
                if self.order_db is not None:
                    self.order_db.mark_failed(order_id)
                return None

        except Exception as e:
            logger.error(f"Order-Platzierung fehlgeschlagen: {e}")
            return None

    def _write_pending_order_direct(
        self,
        symbol: str,
        direction: str,
        volume: float,
        entry_price: Optional[float],
        sl: Optional[float],
        tp: Optional[float],
        signal: Optional[dict] = None,
    ) -> Optional[int]:
        """Schreibt pending_order.json direkt – ohne MT5-Verbindung.

        Liest mt5_common_files_path und mt5_order_file aus der Config.
        Gibt _PENDING_FILE_TICKET zurück bei Erfolg, sonst None.
        """
        try:
            cfg = self._config

            # Pfad bestimmen (gleiche Logik wie MT5Connector._get_common_files_path)
            common_path_str = getattr(cfg, "mt5_common_files_path", "") if cfg else ""
            if common_path_str:
                common_path = Path(common_path_str)
            else:
                appdata = os.environ.get("APPDATA", "")
                if appdata:
                    default = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
                    if default.exists():
                        common_path = default
                    else:
                        output = Path(getattr(cfg, "output_dir", "Output")) if cfg else Path("Output")
                        output.mkdir(exist_ok=True)
                        common_path = output
                else:
                    output = Path(getattr(cfg, "output_dir", "Output")) if cfg else Path("Output")
                    output.mkdir(exist_ok=True)
                    common_path = output

            order_file = getattr(cfg, "mt5_order_file", "pending_order.json") if cfg else "pending_order.json"
            path = common_path / order_file

            # ATR-Parameter für EA-Trade-Management aus Signal extrahieren
            _sig = signal or {}
            atr_val = _safe_float(_sig.get("atr") or _sig.get("atr_value"))
            cfg = self._config
            trailing_mult = (
                getattr(cfg, "trailing_atr_multiplier",
                        getattr(cfg, "trade_management", {}).get("trailing_atr_multiplier", 1.5))
                if cfg else 1.5
            )
            be_mult = (
                getattr(cfg, "breakeven_atr_multiplier",
                        getattr(cfg, "trade_management", {}).get("breakeven_atr_multiplier", 1.0))
                if cfg else 1.0
            )
            pip_size = 0.0001 if symbol not in ("USDJPY", "EURJPY", "GBPJPY") else 0.01
            breakeven_pips = round(atr_val * be_mult / pip_size, 1) if atr_val else None

            order = {
                "created_at": time.time(),
                "timestamp": time.time(),
                "symbol": symbol,
                "direction": "buy" if direction == "long" else "sell",
                "volume": float(volume),
                "sl": sl,
                "tp": tp,
                "comment": "InvestApp",
                "status": "pending",
                # Trade-Management Parameter für den EA
                "atr_value": atr_val,
                "breakeven_trigger_pips": breakeven_pips,
                "trailing_atr_multiplier": trailing_mult,
            }
            with open(path, "w") as f:
                json.dump(order, f, indent=2)

            logger.warning("[Watch] %s | pending_order.json geschrieben (ohne MT5-Connector): %s", symbol, path)
            return _PENDING_FILE_TICKET
        except Exception as e:
            logger.error("[Watch] %s | _write_pending_order_direct fehlgeschlagen: %s", symbol, e)
            return None

    def sync_positions_from_mt5(self) -> None:
        """
        Alle 60 Sekunden: offene MT5-Positionen lesen und DB aktualisieren.

        Architektur: MT5 ist Trade-Eigentümer (Breakeven + Trailing via EA).
        Python liest nur Status, schreibt in DB, triggert Learning Agent bei Close.
        Kein aktives SL/TP-Management von Python-Seite.
        """
        if self.order_db is None:
            return
        if not hasattr(self.connector, "get_open_positions"):
            return

        try:
            mt5_positions = self.connector.get_open_positions()
            mt5_tickets = {p["ticket"] for p in mt5_positions}

            # ── Offene Positionen in DB aktualisieren ─────────────────────
            for pos in mt5_positions:
                ticket = pos["ticket"]
                current_price = pos.get("current_price", 0.0)
                current_sl = pos.get("sl", 0.0)
                direction_raw = pos.get("type", pos.get("direction", ""))
                direction = "LONG" if direction_raw in ("long", "buy") else "SHORT"

                # Bestehenden Datensatz holen für max/min-Berechnung
                existing = self.order_db.get_order_by_ticket(ticket)
                if existing:
                    max_p = existing.get("max_price_reached") or current_price
                    min_p = existing.get("min_price_reached") or current_price
                    if direction == "LONG":
                        max_p = max(max_p, current_price)
                    else:
                        min_p = min(min_p, current_price)

                    if hasattr(self.order_db, "update_trade_progress"):
                        self.order_db.update_trade_progress(
                            ticket=ticket,
                            max_price=max_p,
                            min_price=min_p,
                            last_sl=current_sl,
                            last_checked_at=datetime.now(timezone.utc).isoformat(),
                        )
                else:
                    # Neue MT5-Position in DB eintragen
                    self.order_db.upsert_open_position(
                        symbol=pos["symbol"],
                        direction=pos.get("direction", "buy"),
                        ticket=ticket,
                        lot_size=pos.get("volume", 0),
                        entry_price=pos.get("open_price", 0),
                        sl=current_sl,
                        tp=pos.get("tp", 0),
                        profit=pos.get("profit", 0),
                    )

            # ── Geschlossene Trades erkennen ───────────────────────────────
            db_tickets = self.order_db.get_all_open_tickets()
            closed_tickets = db_tickets - mt5_tickets

            for ticket in closed_tickets:
                self._handle_trade_closed(ticket)

            self._last_sync_ts = datetime.now(timezone.utc).timestamp()

        except Exception as e:
            logger.error(f"[Watch-Agent] sync_positions_from_mt5 Fehler: {e}")

    def _handle_trade_closed(self, ticket: int) -> None:
        """
        Trade wurde von MT5 geschlossen – Details aus History holen und DB aktualisieren.
        Kein SL/TP-Eingriff, nur Zustandsaufzeichnung und Learning-Trigger.
        """
        exit_price = None
        pnl_pips = None
        pnl_currency = None
        exit_reason = "UNKNOWN"
        closed_at = datetime.now(timezone.utc).isoformat()

        # History aus MT5 holen (bevorzugt)
        if hasattr(self.connector, "get_deals_history"):
            try:
                history = self.connector.get_deals_history(ticket)
                if history:
                    exit_price = history.get("exit_price")
                    pnl_currency = history.get("profit")
                    exit_reason = history.get("reason", "UNKNOWN")
                    closed_at = history.get("closed_at") or closed_at
            except Exception as e:
                logger.warning(f"[Watch] get_deals_history Fehler für Ticket {ticket}: {e}")
        elif hasattr(self.connector, "get_closed_deals"):
            try:
                since = self._last_sync_ts or (datetime.now(timezone.utc).timestamp() - 3600)
                deals = self.connector.get_closed_deals(since)
                for d in deals:
                    if d.get("ticket") == ticket:
                        exit_price = d.get("close_price")
                        pnl_currency = d.get("profit")
                        break
            except Exception as e:
                logger.warning(f"[Watch] get_closed_deals Fehler: {e}")

        # Pips aus Währungsgewinn schätzen (Fallback)
        if pnl_currency is not None:
            order_info = self.order_db.get_order_by_ticket(ticket) or {}
            entry = float(order_info.get("entry_price") or 0.0)
            if exit_price and entry:
                raw_dir = order_info.get("direction", "buy")
                if raw_dir in ("buy", "long"):
                    pnl_pips = round((exit_price - entry) / 0.0001, 1)
                else:
                    pnl_pips = round((entry - exit_price) / 0.0001, 1)

        # DB aktualisieren
        if hasattr(self.order_db, "mark_trade_closed"):
            self.order_db.mark_trade_closed(
                ticket=ticket,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_pips=pnl_pips,
                pnl_currency=pnl_currency,
                closed_at=closed_at,
            )
        else:
            self.order_db.update_order_status(
                ticket=ticket,
                status="closed",
                close_price=exit_price,
                pnl=pnl_currency,
            )

        pnl_str = f"{pnl_currency:+.2f}" if pnl_currency is not None else "n/a"
        logger.info(
            "[Watch] Trade geschlossen: Ticket=%s | Grund=%s | PnL=%s pips | PnL=%s",
            ticket, exit_reason, pnl_pips, pnl_str,
        )

        # Tages-Log + Archivierung wie bisher
        order_info = self.order_db.get_order_by_ticket(ticket) or {}
        symbol = order_info.get("symbol", "")
        direction = order_info.get("direction", "")
        pnl_val = pnl_currency or 0.0

        if symbol:
            try:
                from utils.verbose_display import print_order_event
                print_order_event("close", symbol, {
                    "direction": direction,
                    "entry_price": float(order_info.get("entry_price") or 0.0),
                    "sl": float(order_info.get("sl") or 0.0),
                    "tp": float(order_info.get("tp") or 0.0),
                    "crv": float(order_info.get("crv") or 0.0),
                    "ticket": ticket,
                    "pnl": pnl_val,
                }, self._config)
            except Exception:
                pass

        if self.db is not None and order_info:
            try:
                archive = {
                    "id": order_info.get("id", str(uuid.uuid4())),
                    "signal_id": order_info.get("signal_id") or order_info.get("id", ""),
                    "mt5_ticket": ticket,
                    "instrument": symbol,
                    "direction": direction,
                    "entry_price": order_info.get("entry_price", 0.0),
                    "sl": order_info.get("sl", 0.0),
                    "tp": order_info.get("tp", 0.0),
                    "lot_size": order_info.get("lot_size", 0.0),
                    "status": "closed",
                    "close_price": exit_price,
                    "pnl": pnl_currency,
                    "close_time": None,
                }
                self.db.save_trade(archive)
            except Exception as _e:
                logger.warning(f"[Watch-Agent] invest_app.db Archivierung Fehler: {_e}")

        if self.cycle_logger is not None and symbol:
            outcome = "win" if pnl_val > 0 else ("loss" if pnl_val < 0 else "breakeven")
            try:
                self.cycle_logger.log_order(
                    event="close",
                    symbol=symbol,
                    direction=str(direction),
                    entry=float(order_info.get("entry_price") or 0.0),
                    sl=float(order_info.get("sl") or 0.0),
                    tp=float(order_info.get("tp") or 0.0),
                    crv=float(order_info.get("crv") or 0.0),
                    confidence=float(order_info.get("confidence") or 0.0),
                    agent_params={"ticket": ticket, "pnl": pnl_val},
                )
                self.cycle_logger.log_trade_result(
                    symbol=symbol,
                    direction=str(direction),
                    pnl_pips=pnl_pips or pnl_val,
                    outcome=outcome,
                    agent_params=order_info,
                )
            except Exception as e:
                logger.warning(f"CycleLogger log_trade_result Fehler: {e}")

        # Learning Agent triggern
        self._trigger_learning_analysis(ticket)

    def _trigger_learning_analysis(self, ticket: int) -> None:
        """Triggert den Learning Agent für einen abgeschlossenen Trade."""
        if not hasattr(self, "_learning_agent") or self._learning_agent is None:
            return
        try:
            self._learning_agent.analyze_closed_trade(ticket)
            self._learning_agent.check_and_apply_config_adjustments()
        except Exception as e:
            logger.warning(f"[Watch] Learning-Analyse für Ticket {ticket} fehlgeschlagen: {e}")

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
