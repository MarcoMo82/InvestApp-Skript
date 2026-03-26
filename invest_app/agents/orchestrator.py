"""
Orchestrator: Hauptsteuerung der Agent-Pipeline.
Führt alle Agenten sequenziell aus und aggregiert die Ergebnisse zu einem Signal.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from agents.macro_agent import MacroAgent, SAFE_HAVEN_SYMBOLS
from agents.trend_agent import TrendAgent
from agents.volatility_agent import VolatilityAgent
from agents.level_agent import LevelAgent
from agents.entry_agent import EntryAgent
from agents.risk_agent import RiskAgent
from agents.validation_agent import ValidationAgent
from agents.reporting_agent import ReportingAgent
from agents.learning_agent import LearningAgent
from agents.chart_exporter import ChartExporter
from models.signal import Signal, SignalStatus, Direction
from models.trade import Trade
from utils.logger import get_logger
from utils.database import Database
from utils.correlation import has_correlated_open_position
from utils.session import get_current_session, is_trend_trading_allowed, get_session_bonus

if TYPE_CHECKING:
    from agents.watch_agent import WatchAgent

logger = get_logger(__name__)


class Orchestrator:
    """
    Hauptorchestrator der InvestApp Trading-Pipeline.

    Ablauf pro Zyklus:
    1. Für jedes Symbol: Macro → Trend → Volatility → Level → Entry → Risk → Validation
    2. Signale aggregieren und ranken
    3. Reporting
    4. Optionale Trade-Ausführung (nur mit expliziter Freigabe)
    """

    def __init__(
        self,
        config: Any,
        connector: Any,  # MT5Connector oder YFinanceConnector
        macro_agent: MacroAgent,
        trend_agent: TrendAgent,
        volatility_agent: VolatilityAgent,
        level_agent: LevelAgent,
        entry_agent: EntryAgent,
        risk_agent: RiskAgent,
        validation_agent: ValidationAgent,
        reporting_agent: ReportingAgent,
        database: Database,
        learning_agent: Optional[LearningAgent] = None,
        watch_agent: Optional["WatchAgent"] = None,
        chart_exporter: Optional[ChartExporter] = None,
        scanner_agent: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.connector = connector
        self.macro_agent = macro_agent
        self.trend_agent = trend_agent
        self.volatility_agent = volatility_agent
        self.level_agent = level_agent
        self.entry_agent = entry_agent
        self.risk_agent = risk_agent
        self.validation_agent = validation_agent
        self.reporting_agent = reporting_agent
        self.learning_agent = learning_agent
        self.watch_agent = watch_agent
        self.chart_exporter = chart_exporter
        self.scanner_agent = scanner_agent
        self.active_symbols: list = list(getattr(config, "all_symbols", []))
        self.db = database

        self._scheduler: Optional[BackgroundScheduler] = None
        self._kill_switch = threading.Event()
        self._cycle_count = 0
        self._daily_pnl = 0.0
        self._daily_loss_triggered: bool = False
        self._last_cycle_date: Optional[object] = None

    def run_cycle(self) -> list[Signal]:
        """
        Führt einen vollständigen Analyse-Zyklus für alle konfigurierten Symbole durch.

        Returns:
            Liste aller erzeugten Signale (approved + rejected)
        """
        if self._kill_switch.is_set():
            logger.warning("Kill-Switch aktiv – Zyklus übersprungen.")
            return []

        # P1.2: Tages-Reset
        today = datetime.now(timezone.utc).date()
        if self._last_cycle_date != today:
            self._last_cycle_date = today
            self._daily_loss_triggered = False
            logger.debug("Neuer Tag – Daily-Loss-Flag zurückgesetzt.")

        # P1.2: Daily Drawdown Check
        if getattr(self.config, "drawdown_enabled", True) and not self._check_daily_drawdown():
            logger.warning("Daily Drawdown Limit erreicht – kein weiteres Trading heute")
            return []

        # P1.1 + P2.1: Offene Positionen einmalig pro Zyklus ermitteln
        open_positions = 0
        open_symbols: list[str] = []
        if hasattr(self.connector, "get_open_positions"):
            try:
                positions = self.connector.get_open_positions()
                open_positions = len(positions)
                open_symbols = [p.get("symbol", "") for p in positions if p.get("symbol")]
            except Exception as e:
                logger.debug(f"get_open_positions Fehler: {e}")
                if hasattr(self.connector, "get_open_positions_count"):
                    try:
                        open_positions = self.connector.get_open_positions_count()
                    except Exception as e2:
                        logger.debug(f"get_open_positions_count Fehler: {e2}")
        elif hasattr(self.connector, "get_open_positions_count"):
            try:
                open_positions = self.connector.get_open_positions_count()
            except Exception as e:
                logger.debug(f"get_open_positions_count Fehler: {e}")

        # P2.3: Risk-Sentiment einmalig pro Zyklus ermitteln
        risk_sentiment = "neutral"
        if getattr(self.config, "safe_haven_enabled", True):
            try:
                vix_threshold = float(getattr(self.config, "vix_risk_off_threshold", 20.0))
                risk_sentiment = self.macro_agent.get_risk_sentiment(vix_threshold)
                if risk_sentiment != "neutral":
                    logger.info(f"Risk-Sentiment: {risk_sentiment}")
            except Exception as e:
                logger.debug(f"Risk-Sentiment Fehler: {e}")

        self._cycle_count += 1
        cycle_id = f"cycle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{self._cycle_count}"
        logger.info(f"=== Zyklus {self._cycle_count} gestartet ({cycle_id}) ===")

        symbols = self.active_symbols if self.active_symbols else getattr(self.config, "all_symbols", [])

        if getattr(self.config, "show_cycle_banner", True):
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n{'─' * 50}")
            print(f" Zyklus #{self._cycle_count} | {now} | {len(symbols)} Symbole")
            print(f"{'─' * 50}")

        all_signals: list[Signal] = []

        for symbol in symbols:
            try:
                signal = self._analyze_symbol(
                    symbol,
                    open_positions=open_positions,
                    open_symbols=open_symbols,
                    risk_sentiment=risk_sentiment,
                )
                if signal:
                    all_signals.append(signal)
                    self.db.save_signal(signal)
                    if self.chart_exporter is not None:
                        self.chart_exporter.export_zones(
                            symbol, signal.agent_scores or {}, signal
                        )
            except Exception as e:
                logger.error(f"Fehler bei {symbol}: {e}", exc_info=True)

        # Chart-Export speichern
        if self.chart_exporter is not None:
            try:
                self.chart_exporter.save()
            except Exception as e:
                logger.warning(f"ChartExporter Fehler: {e}")

        # Reporting
        if all_signals:
            self.reporting_agent.run({"signals": all_signals, "cycle_id": cycle_id})

        # Learning (nicht-blockierend, nach Reporting)
        if self.learning_agent is not None:
            try:
                self.learning_agent.run_post_cycle([])
            except Exception as e:
                logger.warning(f"LearningAgent Fehler: {e}")

        approved = [s for s in all_signals if s.status == SignalStatus.APPROVED]

        # Signale weiterleiten: Watch-Agent übernimmt Ausführung (kein doppelter place_order)
        trading_mode = getattr(self.config, "trading_mode", "analysis")
        for signal in approved:
            instrument = signal.instrument
            signal_dict = signal.model_dump(mode="json")
            if self.watch_agent is not None:
                self.watch_agent.add_pending_signal(signal_dict)
                logger.info(f"Signal an Watch-Agent übergeben: {instrument}")
            elif trading_mode in ("demo", "live"):
                # Fallback: direkter Market-Entry (nur in demo/live Modus)
                self._place_and_save_order(signal)

        # Positions-Status überwachen (nur Logging + Daily-Loss, kein Partial-Exit)
        self._monitor_open_positions()

        logger.info(
            f"=== Zyklus {self._cycle_count} abgeschlossen | "
            f"Signale: {len(all_signals)} | Freigegeben: {len(approved)} ==="
        )
        return all_signals

    def _analyze_symbol(
        self,
        symbol: str,
        open_positions: int = 0,
        open_symbols: Optional[list] = None,
        risk_sentiment: str = "neutral",
    ) -> Optional[Signal]:
        """Führt die vollständige Agent-Pipeline für ein Symbol aus."""
        logger.debug(f"Analysiere {symbol} ...")

        # Marktdaten laden
        try:
            ohlcv_htf = self.connector.get_ohlcv(symbol, self.config.htf_timeframe, self.config.htf_bars)
            ohlcv_entry = self.connector.get_ohlcv(symbol, self.config.entry_timeframe, self.config.entry_bars)
            price_data = self.connector.get_current_price(symbol)
        except Exception as e:
            logger.warning(f"Daten für {symbol} nicht verfügbar: {e}")
            return None

        if ohlcv_htf.empty:
            logger.debug(f"Keine HTF-Daten für {symbol}")
            return None

        current_price = price_data.get("ask", float(ohlcv_htf["close"].iloc[-1]))

        # 1. Makro-Analyse
        macro_result = self.macro_agent.run({"symbol": symbol})
        if not macro_result.get("trading_allowed", True):
            logger.debug(f"{symbol}: Makro-Freigabe verweigert")
            return self._build_rejected_signal(symbol, "neutral", macro_result, {}, {}, {}, {}, {}, {})

        # P1.4: News-Block – sperrt Signale ±30 Min um High-Impact Events
        if getattr(self.config, "news_block_enabled", True):
            minutes_before = getattr(self.config, "news_block_minutes_before", 30)
            minutes_after = getattr(self.config, "news_block_minutes_after", 30)
            blocked, block_reason = self.macro_agent.check_news_block(
                symbol,
                minutes_before=minutes_before,
                minutes_after=minutes_after,
            )
            if blocked:
                logger.info(f"[Orchestrator] {symbol} NEWS-BLOCK: {block_reason}")
                return self._build_rejected_signal(
                    symbol, "neutral", macro_result, {}, {}, {}, {}, {}, {}
                )

        # P2.1: Korrelations-Check – kein Trade wenn korreliertes Symbol bereits offen
        if getattr(self.config, "correlation_check_enabled", True) and open_symbols:
            blocked, blocking_sym = has_correlated_open_position(symbol, open_symbols)
            if blocked:
                logger.debug(
                    f"{symbol}: Korrelations-Block – {blocking_sym} bereits offen"
                )
                return self._build_rejected_signal(
                    symbol, "neutral", macro_result, {}, {}, {}, {}, {}, {}
                )

        # 2. Trend-Analyse
        trend_result = self.trend_agent.run({"symbol": symbol, "ohlcv": ohlcv_htf})
        direction = trend_result.get("direction", "neutral")
        if direction in ("neutral", "sideways"):
            logger.debug(f"{symbol}: Kein klarer Trend ({direction})")
            return None

        # P2.2: Asian-Session-Block – kein Trend-Trading in der Asian Session
        if not is_trend_trading_allowed(self.config):
            logger.debug(f"{symbol}: Asian Session – Trend-Trading blockiert")
            return None

        # 3. Volatilitäts-Analyse
        vol_result = self.volatility_agent.run({"symbol": symbol, "ohlcv": ohlcv_htf})
        if not vol_result.get("setup_allowed", False):
            logger.debug(f"{symbol}: Volatilitäts-Freigabe verweigert")
            return self._build_rejected_signal(symbol, direction, macro_result, trend_result, vol_result, {}, {}, {}, {})

        # 4. Level-Analyse
        level_result = self.level_agent.run({
            "symbol": symbol,
            "ohlcv": ohlcv_htf,
            "current_price": current_price,
        })

        # 5. Entry-Analyse (P1.3: aktuellen Spread übergeben)
        spread_pips = 0.0
        if hasattr(self.connector, "get_current_spread_pips"):
            try:
                spread_pips = self.connector.get_current_spread_pips(symbol)
            except Exception as e:
                logger.debug(f"get_current_spread_pips Fehler für {symbol}: {e}")

        entry_result = self.entry_agent.run({
            "symbol": symbol,
            "ohlcv_entry": ohlcv_entry,
            "direction": direction,
            "nearest_level": level_result.get("nearest_level"),
            "atr_value": vol_result.get("atr_value", 0.0),
            "current_spread_pips": spread_pips,
        })

        if not entry_result.get("entry_found", False):
            logger.debug(f"{symbol}: Kein Entry-Setup")
            return None

        # 6. Risk-Analyse (P1.1: open_positions übergeben)
        balance = self.connector.get_account_balance()
        risk_result = self.risk_agent.run({
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_result.get("entry_price", current_price),
            "atr_value": vol_result.get("atr_value", 0.0),
            "account_balance": balance,
            "open_positions": open_positions,
        })

        if not risk_result.get("trade_allowed", False):
            logger.debug(f"{symbol}: Risk-Gate abgelehnt – {risk_result.get('rejection_reason')}")
            return self._build_rejected_signal(symbol, direction, macro_result, trend_result, vol_result, level_result, entry_result, risk_result, {})

        # 7. Validation
        validation_result = self.validation_agent.run({
            "symbol": symbol,
            "macro": macro_result,
            "trend": trend_result,
            "volatility": vol_result,
            "level": level_result,
            "entry": entry_result,
            "risk": risk_result,
        })

        # Signal zusammenbauen
        signal = Signal(
            instrument=symbol,
            direction=Direction(direction),
            trend_status=trend_result.get("structure_status", ""),
            macro_status=f"{macro_result.get('macro_bias', 'neutral')} | risk: {macro_result.get('event_risk', 'medium')}",
            entry_price=entry_result.get("entry_price", 0.0),
            stop_loss=risk_result.get("stop_loss", 0.0),
            take_profit=risk_result.get("take_profit", 0.0),
            crv=risk_result.get("crv", 0.0),
            lot_size=risk_result.get("lot_size", 0.0),
            confidence_score=validation_result.get("confidence_score", 0.0),
            reasoning=validation_result.get("summary", ""),
            pros=validation_result.get("pros", []),
            cons=validation_result.get("cons", []),
            agent_scores={
                "macro": macro_result,
                "trend": trend_result,
                "volatility": vol_result,
                "level": level_result,
                "entry": entry_result,
                "risk": risk_result,
                "validation": validation_result,
            },
        )

        # P2.4: Session-Scoring – Confidence-Bonus vor Schwellwert-Prüfung
        if getattr(self.config, "session_scoring_enabled", True):
            session_bonus = get_session_bonus(symbol, self.config)
            if session_bonus > 0:
                old_score = signal.confidence_score
                signal.confidence_score = min(100.0, old_score + session_bonus)
                logger.debug(
                    f"{symbol}: Session-Bonus +{session_bonus} "
                    f"({old_score:.1f} → {signal.confidence_score:.1f})"
                )

        # P2.3: Safe-Haven Logik bei Risk-Off
        if getattr(self.config, "safe_haven_enabled", True) and risk_sentiment == "risk_off":
            is_safe_haven = symbol in SAFE_HAVEN_SYMBOLS
            if is_safe_haven:
                bonus = int(getattr(self.config, "safe_haven_confidence_bonus", 10))
                old_score = signal.confidence_score
                signal.confidence_score = min(100.0, old_score + bonus)
                logger.debug(
                    f"{symbol}: Safe-Haven Bonus +{bonus} bei Risk-Off "
                    f"({old_score:.1f} → {signal.confidence_score:.1f})"
                )
            else:
                # Nicht-Safe-Haven bei Risk-Off: verwerfen wenn unter 75%
                if signal.confidence_score < 75.0:
                    logger.debug(
                        f"{symbol}: Risk-Off – kein Safe-Haven, Score zu niedrig "
                        f"({signal.confidence_score:.1f} < 75)"
                    )
                    signal.status = SignalStatus.REJECTED
                    return signal

        # Status setzen
        min_score = float(getattr(self.config, "min_confidence_score", 80.0))
        if validation_result.get("validated", False) and signal.confidence_score >= min_score:
            signal.status = SignalStatus.APPROVED
            logger.info(f"✅ Signal FREIGEGEBEN: {signal.summary()}")
        else:
            signal.status = SignalStatus.REJECTED
            logger.debug(f"❌ Signal VERWORFEN: {signal.summary()}")

        return signal

    def _build_rejected_signal(
        self, symbol: str, direction: str, macro: dict, trend: dict,
        vol: dict, level: dict, entry: dict, risk: dict, validation: dict
    ) -> Signal:
        """Erstellt ein abgelehntes Signal für die Datenbank."""
        return Signal(
            instrument=symbol,
            direction=Direction(direction) if direction in ("long", "short") else Direction.NEUTRAL,
            trend_status=trend.get("structure_status", ""),
            macro_status=macro.get("macro_bias", "neutral"),
            confidence_score=0.0,
            status=SignalStatus.REJECTED,
            reasoning="Frühzeitig abgelehnt durch Agenten-Gatekeeping",
            agent_scores={"macro": macro, "trend": trend, "volatility": vol},
        )

    def start_scheduler(self) -> None:
        """Startet den APScheduler für automatische Zyklen alle 5 Minuten."""
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            func=self.run_cycle,
            trigger=IntervalTrigger(minutes=self.config.cycle_interval_minutes),
            id="main_cycle",
            name="InvestApp Hauptzyklus",
            replace_existing=True,
        )
        if self.watch_agent is not None:
            self._scheduler.add_job(
                func=self.watch_agent.run_watch_cycle,
                trigger=IntervalTrigger(minutes=1),
                id="watch_agent_cycle",
                name="Watch-Agent (1min)",
                replace_existing=True,
            )
            logger.info("Watch-Agent gestartet (1-Minuten-Intervall).")
        if self.scanner_agent is not None:
            scanner_interval = getattr(self.config, "scanner_interval_minutes", 60)
            self._scheduler.add_job(
                func=self._run_scanner,
                trigger=IntervalTrigger(minutes=scanner_interval),
                id="scanner_cycle",
                name=f"Scanner ({scanner_interval}min)",
                replace_existing=True,
            )
            logger.info(f"Scanner-Job gestartet ({scanner_interval}-Minuten-Intervall).")
        self._scheduler.start()
        logger.info(
            f"Scheduler gestartet – Zyklus alle {self.config.cycle_interval_minutes} Minuten."
        )

    def stop_scheduler(self) -> None:
        """Stoppt den Scheduler sauber."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler gestoppt.")

    def _run_scanner(self) -> None:
        """Führt einen Scanner-Lauf durch und aktualisiert active_symbols.
        Fallback auf config.fallback_symbols wenn Scanner deaktiviert oder scan() leer zurückgibt.
        """
        if self.scanner_agent is None:
            self.active_symbols = list(getattr(self.config, "all_symbols", []))
            return
        try:
            logger.info("[Orchestrator] Scanner: Lade Symbole...")
            previous = list(self.active_symbols)
            results = self.scanner_agent.scan()
            if results:
                self.active_symbols = results
                self.scanner_agent.log_watchlist(previous if previous else None)
                top_str = ", ".join(self.active_symbols[:5])
                logger.info(
                    f"[Scanner] {len(self.active_symbols)} ausgewählt: {top_str}"
                    + (" ..." if len(self.active_symbols) > 5 else "")
                )
            else:
                self.active_symbols = list(getattr(self.config, "all_symbols", []))
                logger.info(f"[Scanner] scan() leer – Fallback auf {len(self.active_symbols)} Fallback-Symbole")
        except Exception as e:
            logger.warning(f"[Scanner] Scan fehlgeschlagen – Fallback auf config.fallback_symbols: {e}")
            if not self.active_symbols:
                self.active_symbols = list(getattr(self.config, "all_symbols", []))

    def activate_kill_switch(self) -> None:
        """Aktiviert den Kill-Switch – unterbricht alle weiteren Zyklen."""
        self._kill_switch.set()
        logger.warning("KILL-SWITCH AKTIVIERT – keine weiteren Zyklen.")

    def deactivate_kill_switch(self) -> None:
        """Deaktiviert den Kill-Switch."""
        self._kill_switch.clear()
        logger.info("Kill-Switch deaktiviert.")

    def _place_and_save_order(self, signal: Signal) -> None:
        """
        Fallback: Platziert eine Order direkt wenn kein Watch-Agent vorhanden.
        Wird nur genutzt wenn self.watch_agent is None und trading_mode in (demo, live).
        """
        try:
            ticket = self.connector.place_order(signal) if hasattr(self.connector, "place_order") else None
            if ticket:
                trade = Trade(
                    signal_id=signal.id,
                    mt5_ticket=ticket,
                    instrument=signal.instrument,
                    direction=str(signal.direction.value) if hasattr(signal.direction, "value") else str(signal.direction),
                    entry_price=signal.entry_price,
                    sl=signal.stop_loss,
                    tp=signal.take_profit,
                    lot_size=signal.lot_size,
                    open_time=datetime.now(timezone.utc),
                    status="open",
                )
                self.db.save_trade(trade)
                logger.info(f"Fallback-Order platziert: {signal.instrument} Ticket={ticket}")
            else:
                logger.warning(f"Fallback-Order fehlgeschlagen für {signal.instrument}")
        except Exception as e:
            logger.error(f"Fallback-Order Fehler für {signal.instrument}: {e}")

    def _check_daily_drawdown(self) -> bool:
        """
        Prüft tägliches Drawdown-Limit. Setzt _daily_loss_triggered wenn überschritten.

        Returns:
            True  → Trading erlaubt
            False → Limit überschritten, Trading gestoppt
        """
        if self._daily_loss_triggered:
            return False

        try:
            account_balance = (
                self.connector.get_account_balance()
                if hasattr(self.connector, "get_account_balance")
                else 10000.0
            )
            max_loss = account_balance * self.config.max_daily_loss
            # Basis: DB-Wert
            daily_pnl = self.db.get_daily_pnl()

            # MT5-History bevorzugen wenn Connector wirklich verbunden (kein Mock)
            connected = getattr(self.connector, "_connected", False)
            if connected is True and hasattr(self.connector, "get_today_realized_pnl"):
                try:
                    daily_pnl = self.connector.get_today_realized_pnl()
                except Exception:
                    pass  # DB-Wert bleibt

            if daily_pnl < -max_loss:
                self._daily_loss_triggered = True
                logger.warning(
                    f"Daily Drawdown Limit erreicht: {daily_pnl:.2f} "
                    f"(Limit: -{max_loss:.2f})"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Daily drawdown check Fehler: {e}")
            return True  # Im Fehlerfall: weitermachen

    def _check_daily_loss_limit(self) -> bool:
        """
        Prüft ob das tägliche Verlustlimit noch nicht überschritten wurde.

        Returns:
            True  → Trading erlaubt
            False → Limit überschritten, Trading stoppen
        """
        try:
            daily_pnl = self.db.get_daily_pnl()
            account_balance = (
                self.connector.get_account_balance()
                if hasattr(self.connector, "get_account_balance")
                else 10000.0
            )
            max_loss = account_balance * self.config.max_daily_loss

            if daily_pnl < -max_loss:
                logger.warning(
                    f"Daily Loss Limit erreicht: {daily_pnl:.2f} (Limit: -{max_loss:.2f})"
                )
                return False  # Stoppe Trading
            return True
        except Exception as e:
            logger.error(f"Daily loss check Fehler: {e}")
            return True  # Im Fehlerfall: weitermachen

    def _monitor_open_positions(self) -> None:
        """
        Gleicht offene DB-Trades mit aktiven MT5-Positionen ab.
        Schließt Trades in der DB die in MT5 nicht mehr offen sind.
        """
        if not hasattr(self.connector, "get_open_positions"):
            return

        try:
            db_open = self.db.get_open_trades()
            if not db_open:
                return

            mt5_positions = self.connector.get_open_positions()
            mt5_tickets = {p["ticket"] for p in mt5_positions}

            for trade in db_open:
                ticket = trade.get("mt5_ticket")
                if ticket and ticket not in mt5_tickets:
                    # Echten Close-Preis und PnL aus MT5-Deal-History holen
                    close_price = 0.0
                    pnl = 0.0
                    if hasattr(self.connector, "get_deal_by_ticket"):
                        deal = self.connector.get_deal_by_ticket(ticket)
                        if deal:
                            close_price = deal.get("price", 0.0)
                            pnl = deal.get("profit", 0.0)
                        else:
                            logger.warning(
                                f"Deal-Daten für Ticket {ticket} nicht abrufbar – Fallback 0.0"
                            )
                    self.db.update_trade_close(
                        ticket=ticket,
                        close_price=close_price,
                        pnl=pnl,
                        close_time=datetime.now(timezone.utc),
                    )
                    logger.info(
                        f"Position {ticket} geschlossen: "
                        f"Close-Preis={close_price:.5f}, PnL={pnl:.2f}"
                    )

            self.db.update_performance()

        except Exception as e:
            logger.error(f"Position-Monitoring Fehler: {e}")
