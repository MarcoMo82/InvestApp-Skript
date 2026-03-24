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

from agents.macro_agent import MacroAgent
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

    def run_cycle(self) -> list[Signal]:
        """
        Führt einen vollständigen Analyse-Zyklus für alle konfigurierten Symbole durch.

        Returns:
            Liste aller erzeugten Signale (approved + rejected)
        """
        if self._kill_switch.is_set():
            logger.warning("Kill-Switch aktiv – Zyklus übersprungen.")
            return []

        # Daily Loss Check
        if not self._check_daily_loss_limit():
            logger.warning("Daily-Loss-Limit erreicht – Zyklus übersprungen.")
            return []

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
                signal = self._analyze_symbol(symbol)
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

    def _analyze_symbol(self, symbol: str) -> Optional[Signal]:
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

        # 2. Trend-Analyse
        trend_result = self.trend_agent.run({"symbol": symbol, "ohlcv": ohlcv_htf})
        direction = trend_result.get("direction", "neutral")
        if direction in ("neutral", "sideways"):
            logger.debug(f"{symbol}: Kein klarer Trend ({direction})")
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

        # 5. Entry-Analyse
        entry_result = self.entry_agent.run({
            "symbol": symbol,
            "ohlcv_entry": ohlcv_entry,
            "direction": direction,
            "nearest_level": level_result.get("nearest_level"),
            "atr_value": vol_result.get("atr_value", 0.0),
        })

        if not entry_result.get("entry_found", False):
            logger.debug(f"{symbol}: Kein Entry-Setup")
            return None

        # 6. Risk-Analyse
        balance = self.connector.get_account_balance()
        risk_result = self.risk_agent.run({
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_result.get("entry_price", current_price),
            "atr_value": vol_result.get("atr_value", 0.0),
            "account_balance": balance,
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

        # Status setzen
        if validation_result.get("validated", False) and signal.confidence_score >= self.config.min_confidence_score:
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
        Fallback auf config.all_symbols wenn Scanner deaktiviert oder scan() leer zurückgibt.
        """
        if self.scanner_agent is None:
            self.active_symbols = list(getattr(self.config, "all_symbols", []))
            return
        try:
            previous = list(self.active_symbols)
            results = self.scanner_agent.scan()
            if results:
                self.active_symbols = results
                self.scanner_agent.log_watchlist(previous if previous else None)
                logger.info(f"[Scanner] {len(self.active_symbols)} aktive Symbole nach Scan")
            else:
                self.active_symbols = list(getattr(self.config, "all_symbols", []))
                logger.info(f"[Scanner] scan() leer – Fallback auf {len(self.active_symbols)} config-Symbole")
        except Exception as e:
            logger.warning(f"[Scanner] Scan fehlgeschlagen – Fallback auf config.all_symbols: {e}")
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

    def _monitor_open_positions(self) -> None:
        """
        Überwacht offene Positionen.
        Nur Status-Logging und tägliches Loss-Limit – kein Partial-Exit oder Trailing-Stop.
        Positions-Verwaltung gehört vollständig zum Watch-Agent.
        """
        if self._check_daily_loss_limit():
            logger.warning("_monitor_open_positions: Daily-Loss-Limit erreicht.")
            return
        try:
            open_trades = self.db.get_open_trades() if hasattr(self.db, "get_open_trades") else []
            if open_trades:
                logger.info(f"Offene Positionen: {len(open_trades)}")
        except Exception as e:
            logger.debug(f"Positions-Status nicht verfügbar: {e}")

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
                    # Trade in MT5 geschlossen – DB aktualisieren
                    self.db.update_trade_close(
                        ticket=ticket,
                        close_price=trade.get("entry_price", 0.0),
                        pnl=0.0,
                        close_time=datetime.utcnow(),
                    )
                    logger.info(f"Position {ticket} in MT5 geschlossen – DB aktualisiert.")

            self.db.update_performance()

        except Exception as e:
            logger.error(f"Position-Monitoring Fehler: {e}")
