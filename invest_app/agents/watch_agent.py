"""
Watch-Agent: Überwacht freigegebene Signale und führt Orders aus.
Ist der einzige Agent, der place_order() aufruft.
Prüft Entry-Bedingungen auf dem 1m-Chart bevor eine Order platziert wird.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_MAX_ORDERS_PER_SYMBOL = 2  # Fallback wenn Config fehlt


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
        risk_agent: Optional[Any] = None,
        order_db: Optional[Any] = None,
    ) -> None:
        self.connector = connector
        self.db = db
        self._config = config
        self.simulation_agent = simulation_agent
        self.chart_exporter = chart_exporter
        self.risk_agent = risk_agent
        self.order_db = order_db          # OrderDB-Instanz für persistentes Tracking
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

        with self._lock:
            signals = list(self._pending_signals)

        for signal in signals:
            instrument = signal.get("instrument", "UNKNOWN")
            try:
                ohlcv_1m = self.connector.get_ohlcv(instrument, "1m", 30)
                if ohlcv_1m is None or ohlcv_1m.empty:
                    continue  # bleibt in _pending_signals

                if self._check_entry_condition(signal, ohlcv_1m):
                    ticket = self._place_order(signal)
                    if ticket is not None:
                        executed.append(signal)
                        logger.info(f"Order ausgeführt: {instrument}")
                    else:
                        attempt = signal.get("_retry_count", 0) + 1
                        signal["_retry_count"] = attempt
                        logger.error(f"Order fehlgeschlagen, Retry {attempt}/3: {instrument}")
                        if attempt >= 3:
                            logger.error(f"Order nach 3 Versuchen verworfen: {instrument}")
                            discarded.append(signal)
                        # else: bleibt in _pending_signals für nächsten Versuch
                # else: Bedingung nicht erfüllt → bleibt in _pending_signals
            except Exception as e:
                logger.error(f"Fehler bei Signal-Prüfung {instrument}: {e}")
                # bleibt in _pending_signals

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
            if direction == "long":
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
                        f"[Watch-Agent] ❌ {symbol}: Max. {max_orders} Orders erreicht "
                        f"({count} aktiv) – Signal verworfen"
                    )
                    return None

                if count == 1:
                    max_conf = self.order_db.get_max_confidence(symbol)
                    if confidence <= max_conf:
                        logger.warning(
                            f"[Watch-Agent] ❌ {symbol}: Confidence {confidence:.0f}% ≤ "
                            f"bestehende {max_conf:.0f}% – 2. Order abgelehnt"
                        )
                        return None
                    logger.info(
                        f"[Watch-Agent] 2. Order {symbol}: Confidence {confidence:.0f}% > {max_conf:.0f}% ✓"
                    )

            # ── Order-ID in DB anlegen (status=pending) ─────────────────────
            order_id = None
            if self.order_db is not None:
                order_id = self.order_db.add_order(
                    symbol=symbol,
                    direction=direction,
                    sl=stop_loss or 0.0,
                    tp=take_profit or 0.0,
                    confidence=confidence,
                    lot_size=lot_size,
                )

            # ── Order senden ────────────────────────────────────────────────
            ticket = None
            if hasattr(self.connector, "place_market_order"):
                ticket = self.connector.place_market_order(
                    symbol=symbol,
                    direction=direction,
                    lot_size=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )
            else:
                logger.warning(
                    f"[Watch-Agent] place_market_order nicht verfügbar – {symbol} übersprungen"
                )

            # ── Ergebnis in DB speichern ────────────────────────────────────
            if ticket is not None:
                if self.order_db is not None and order_id is not None:
                    self.order_db.update_ticket(order_id, ticket)
                if self.db is not None:
                    self.db.save_trade(signal)
                logger.info(f"[Watch-Agent] ✅ Order ausgeführt: {symbol} Ticket={ticket}")
                return ticket
            else:
                if self.order_db is not None and order_id is not None:
                    self.order_db.mark_failed(order_id)
                return None

        except Exception as e:
            logger.error(f"Order-Platzierung fehlgeschlagen: {e}")
            return None

    def sync_positions_from_mt5(self) -> None:
        """
        Synchronisiert offene MT5-Positionen mit der OrderDB.
        - Neue MT5-Positionen → in DB eintragen
        - DB-Orders ohne MT5-Position → als 'closed' markieren
        Wird jede Minute aufgerufen.
        """
        if self.order_db is None:
            return
        if not hasattr(self.connector, "get_open_positions"):
            return

        try:
            mt5_positions = self.connector.get_open_positions()
            mt5_tickets = {p["ticket"] for p in mt5_positions}

            # Neue MT5-Positionen in DB eintragen
            for pos in mt5_positions:
                self.order_db.upsert_open_position(
                    symbol=pos["symbol"],
                    direction=pos.get("direction", "buy"),
                    ticket=pos["ticket"],
                    lot_size=pos.get("volume", 0),
                    entry_price=pos.get("open_price", 0),
                    sl=pos.get("sl", 0),
                    tp=pos.get("tp", 0),
                    profit=pos.get("profit", 0),
                )

            # DB-Orders ohne MT5-Position → geschlossen
            db_tickets = self.order_db.get_all_open_tickets()
            closed_tickets = db_tickets - mt5_tickets

            if closed_tickets and hasattr(self.connector, "get_closed_deals"):
                since = self._last_sync_ts or (datetime.now(timezone.utc).timestamp() - 3600)
                deals = self.connector.get_closed_deals(since)
                deals_by_ticket = {d["ticket"]: d for d in deals}

                for ticket in closed_tickets:
                    deal = deals_by_ticket.get(ticket)
                    self.order_db.update_status(
                        ticket=ticket,
                        status="closed",
                        close_price=deal["close_price"] if deal else None,
                        pnl=deal["profit"] if deal else None,
                        closed_at=deal["close_time"] if deal else None,
                    )
                    pnl_str = f"{deal['profit']:+.2f}" if deal else "n/a"
                    logger.info(
                        f"[Watch-Agent] Position geschlossen: Ticket={ticket} PnL={pnl_str}"
                    )
            elif closed_tickets:
                for ticket in closed_tickets:
                    self.order_db.update_status(ticket=ticket, status="closed")

            self._last_sync_ts = datetime.now(timezone.utc).timestamp()

        except Exception as e:
            logger.error(f"[Watch-Agent] sync_positions_from_mt5 Fehler: {e}")

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
