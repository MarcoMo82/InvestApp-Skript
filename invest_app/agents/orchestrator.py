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
from utils.zone_exporter import ZoneExporter
from utils.cycle_logger import CycleLogger

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
        self.zone_exporter = ZoneExporter(config)

        self._scheduler: Optional[BackgroundScheduler] = None
        self._kill_switch = threading.Event()
        self._cycle_count = 0
        self._daily_loss_triggered: bool = False
        self._last_cycle_date: Optional[object] = None

        # Tages-Log
        self.cycle_logger = CycleLogger(config)
        # Wenn watch_agent vorhanden: cycle_logger weitergeben
        if self.watch_agent is not None:
            self.watch_agent.cycle_logger = self.cycle_logger

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

        ts_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        ts_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if getattr(self.config, "show_cycle_banner", True):
            from utils.terminal_display import print_cycle_banner
            print_cycle_banner(self._cycle_count, len(symbols), ts_str)

        # Verbose: Zyklus-Start
        if getattr(self.config, "verbose_terminal_output", True):
            from utils.verbose_display import print_cycle_start
            print_cycle_start(self._cycle_count, list(symbols), ts_str, self.config)

        all_signals: list[Signal] = []
        cycle_results: list[dict] = []

        forecast_count = 0
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
                    # Forecast-Zonen (PENDING) nicht in DB speichern
                    if signal.status != SignalStatus.PENDING:
                        self.db.save_signal(signal)
                    if signal.zone_status == "forecast_zone":
                        forecast_count += 1
                    if self.chart_exporter is not None:
                        self.chart_exporter.export_zones(
                            symbol, signal.agent_scores or {}, signal
                        )
                    # Verbose: Symbol-Analyse ausgeben
                    if getattr(self.config, "verbose_terminal_output", True):
                        from utils.verbose_display import print_symbol_analysis
                        final_status = signal.zone_status or signal.status.value.lower()
                        print_symbol_analysis(
                            symbol, signal.agent_scores or {}, final_status, self.config
                        )
                    # Zyklus-Log Eintrag sammeln
                    cycle_results.append(self._build_cycle_result(signal))
            except Exception as e:
                logger.error(f"Fehler bei {symbol}: {e}", exc_info=True)

        if forecast_count > 0:
            logger.info(f"Forecast-Zonen erkannt: {forecast_count}")

        # Chart-Export speichern
        if self.chart_exporter is not None:
            try:
                self.chart_exporter.save()
            except Exception as e:
                logger.warning(f"ChartExporter Fehler: {e}")

        # Aktive Trades aus DB für Display holen
        active_trade_dicts = self._get_active_trade_dicts()

        # Zone-Export (neues Format)
        try:
            display_dicts = [s.model_dump(mode="json") for s in all_signals]
            self.zone_exporter.export(display_dicts + active_trade_dicts)
        except Exception as e:
            logger.warning(f"ZoneExporter Fehler: {e}")

        # Reporting
        if all_signals or active_trade_dicts:
            self.reporting_agent.run({
                "signals": all_signals,
                "cycle_id": cycle_id,
                "active_trade_dicts": active_trade_dicts,
            })

        # Learning (nicht-blockierend, nach Reporting)
        if self.learning_agent is not None:
            try:
                self.learning_agent.run_post_cycle([])
            except Exception as e:
                logger.warning(f"LearningAgent Fehler: {e}")

        # Tages-Log: Zyklus persistieren
        try:
            self.cycle_logger.log_cycle(
                cycle_nr=self._cycle_count,
                timestamp=ts_iso,
                symbols_analyzed=list(symbols),
                results=cycle_results,
            )
        except Exception as e:
            logger.warning(f"CycleLogger Fehler: {e}")

        approved = [s for s in all_signals if s.status == SignalStatus.APPROVED]
        signal_ready = [s for s in approved if s.zone_status == "signal_ready"]

        if signal_ready:
            logger.info(f"Signale freigegeben: {len(signal_ready)}")

        # Signale weiterleiten: Watch-Agent übernimmt Ausführung (kein doppelter place_order)
        trading_mode = getattr(self.config, "trading_mode", "analysis")
        for signal in signal_ready:
            instrument = signal.instrument
            signal_dict = signal.model_dump(mode="json")
            if self.watch_agent is not None:
                self.watch_agent.add_pending_signal(signal_dict)
                logger.info(f"Signal freigegeben → Watch-Agent: {instrument}")
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
        if direction in ("neutral", "sideways") or trend_result.get("strength_score", 10) <= 4:
            logger.debug(f"{symbol}: Schwacher/kein Trend (direction={direction}, score={trend_result.get('strength_score')})")
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

        # Forecast-Zone Check: Kurs innerhalb 2 ATR der nächsten Zone?
        atr_value_for_zone = vol_result.get("atr_value", 0.0)
        nearest_level = level_result.get("nearest_level")
        is_near_zone = False
        atr_distance: float = 0.0
        if nearest_level and atr_value_for_zone > 0:
            distance_to_zone = abs(nearest_level.get("price", 0.0) - current_price)
            atr_distance = distance_to_zone / atr_value_for_zone
            threshold = getattr(self.config, "forecast_zone_atr_threshold", 2.0)
            is_near_zone = atr_distance <= threshold

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
            if is_near_zone:
                logger.debug(
                    f"{symbol}: Forecast-Zone erkannt – kein Entry-Setup "
                    f"(Distanz: {atr_distance:.2f} ATR)"
                )
                return self._build_forecast_zone_signal(
                    symbol, direction, macro_result, trend_result, vol_result,
                    level_result, atr_distance,
                )
            logger.debug(f"{symbol}: Kein Entry-Setup")
            return None

        # 6. Risk-Analyse (P1.1: open_positions, Handbuch 8.3: Gesamtexposure übergeben)
        balance = self.connector.get_account_balance()
        risk_per_trade = getattr(self.config, "risk_per_trade", 0.01)
        total_open_risk_pct = open_positions * risk_per_trade
        risk_result = self.risk_agent.run({
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_result.get("entry_price", current_price),
            "atr_value": vol_result.get("atr_value", 0.0),
            "account_balance": balance,
            "open_positions": open_positions,
            "total_open_risk_pct": total_open_risk_pct,
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

        # Scanner-Score-Faktoren anhängen (falls Scanner gelaufen ist)
        # Marktkontext für CycleLogger / Learning Agent
        daily_bars = ohlcv_htf.iloc[-96:] if len(ohlcv_htf) >= 96 else ohlcv_htf
        _market_context: dict = {
            "current_price": current_price,
            "daily_high": round(float(daily_bars["high"].max()), 6),
            "daily_low": round(float(daily_bars["low"].min()), 6),
            "spread_pips": spread_pips,
        }

        agent_scores_dict: dict = {
            "macro": macro_result,
            "trend": trend_result,
            "volatility": vol_result,
            "level": level_result,
            "entry": entry_result,
            "risk": risk_result,
            "validation": validation_result,
            "_market_context": _market_context,
        }
        if self.scanner_agent is not None:
            scanner_factors = getattr(self.scanner_agent, "scored_breakdowns", {}).get(symbol)
            if scanner_factors:
                agent_scores_dict["scanner"] = scanner_factors

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
            agent_scores=agent_scores_dict,
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
            signal.zone_status = "signal_ready"
            signal.entry_trigger_hint = self._build_entry_trigger_hint(entry_result, signal)
            logger.info(f"✅ Signal freigegeben: {signal.summary()}")
        else:
            signal.status = SignalStatus.REJECTED
            logger.debug(f"❌ Signal verworfen: {signal.summary()}")

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
                trigger=IntervalTrigger(seconds=getattr(self.config, "watch_interval_seconds", 60)),
                id="watch_agent_cycle",
                name="Watch-Agent",
                replace_existing=True,
            )
            logger.info(f"Watch-Agent gestartet ({getattr(self.config, 'watch_interval_seconds', 15)}s-Intervall).")
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
                    f"[Scanner] Symbole ausgewählt: {len(self.active_symbols)} ({top_str}"
                    + (" ...)" if len(self.active_symbols) > 5 else ")")
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

    def _build_forecast_zone_signal(
        self,
        symbol: str,
        direction: str,
        macro: dict,
        trend: dict,
        vol: dict,
        level: dict,
        atr_distance: float,
    ) -> Signal:
        """Erstellt ein PENDING-Signal für eine erkannte Forecast-Zone."""
        nearest = level.get("nearest_level") or {}
        atr = float(vol.get("atr_value") or 0.0)
        zone_price = float(nearest.get("price") or 0.0)

        # Zonengrenzen aus Level-Typ ableiten
        zone_low = float(
            nearest.get("ob_low") or nearest.get("fvg_low") or (zone_price - atr * 0.5)
        )
        zone_high = float(
            nearest.get("ob_high") or nearest.get("fvg_high") or (zone_price + atr * 0.5)
        )

        agent_scores: dict = {
            "macro": macro,
            "trend": trend,
            "volatility": vol,
            "level": level,
            "_zone_low": zone_low,
            "_zone_high": zone_high,
            "_atr_distance": round(atr_distance, 2),
        }

        return Signal(
            instrument=symbol,
            direction=Direction(direction),
            trend_status=trend.get("structure_status", ""),
            macro_status=f"{macro.get('macro_bias', 'neutral')} | risk: {macro.get('event_risk', 'medium')}",
            confidence_score=0.0,
            status=SignalStatus.PENDING,
            zone_status="forecast_zone",
            entry_trigger_hint="Kurs nähert sich Zone – kein Entry-Setup",
            agent_scores=agent_scores,
        )

    def _build_cycle_result(self, signal: Signal) -> dict:
        """Konvertiert ein Signal in das CycleLogger-JSON-Format."""
        agent_scores = signal.agent_scores or {}
        direction = (
            signal.direction.value
            if hasattr(signal.direction, "value")
            else str(signal.direction)
        )

        # Teildict-Referenzen
        mkt = agent_scores.get("_market_context") or {}
        vol = agent_scores.get("volatility") or {}
        trend = agent_scores.get("trend") or {}
        macro = agent_scores.get("macro") or {}
        entry = agent_scores.get("entry") or {}
        risk = agent_scores.get("risk") or {}
        validation = agent_scores.get("validation") or {}

        # EMA21-Distanz berechnen (% vom aktuellen Preis)
        ema21_distance_pct: float | None = None
        ema_vals = trend.get("ema_values") or {}
        ema21 = ema_vals.get("ema_21")
        ref_close = trend.get("close") or mkt.get("current_price")
        if ema21 and ref_close and float(ref_close) > 0:
            ema21_distance_pct = round(abs(float(ref_close) - float(ema21)) / float(ref_close) * 100, 4)

        # RSI-Zone aus rsi_status ableiten
        rsi_status_raw = vol.get("rsi_status")
        _rsi_zone_map = {
            "overbought": "overbought",
            "oversold": "oversold",
            "above_mid": "bullish",
            "below_mid": "bearish",
            "neutral": "neutral",
        }
        rsi_zone: str | None = _rsi_zone_map.get(rsi_status_raw) if rsi_status_raw else None

        # Trend-Richtung normalisiert
        trend_direction = direction.upper() if direction not in ("neutral", "sideways") else direction

        # Macro-Bias normalisiert
        macro_bias_raw = macro.get("macro_bias") or "neutral"
        macro_bias = macro_bias_raw.upper()

        # Confidence: Signal-Score (nach Session-Bonus etc.) bevorzugen
        confidence: float | None = (
            round(float(signal.confidence_score), 2)
            if signal.confidence_score
            else (float(validation.get("confidence_score")) if validation.get("confidence_score") else None)
        )

        result: dict = {
            "symbol": signal.instrument,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
            "zone_status": signal.zone_status or signal.status.value.lower(),
            "current_price": mkt.get("current_price"),
            "daily_high": mkt.get("daily_high"),
            "daily_low": mkt.get("daily_low"),
            "atr": float(vol["atr_value"]) if vol.get("atr_value") is not None else None,
            "atr_pct": float(vol["atr_pct"]) if vol.get("atr_pct") is not None else None,
            "rsi": float(vol["rsi"]) if vol.get("rsi") is not None else None,
            "rsi_zone": rsi_zone,
            "ema21_distance_pct": ema21_distance_pct,
            "spread": mkt.get("spread_pips"),
            "volatility_phase": vol.get("market_phase"),
            "trend_direction": trend_direction,
            "macro_bias": macro_bias,
            "confidence": confidence,
            "entry_price": (
                float(entry["entry_price"]) if entry.get("entry_price") else
                (float(signal.entry_price) if signal.entry_price else None)
            ),
            "sl": float(risk["stop_loss"]) if risk.get("stop_loss") else None,
            "tp": float(risk["take_profit"]) if risk.get("take_profit") else None,
            "crv": float(risk["crv"]) if risk.get("crv") else None,
            "direction": direction,
            "agents": {},
        }

        # Agents-Unterstruktur (für Kompatibilität mit bestehendem Format)
        if macro:
            result["agents"]["macro"] = {
                "bias": macro.get("macro_bias", "neutral"),
                "event_risk": macro.get("event_risk", "unknown"),
                "approved": bool(macro.get("trading_allowed", True)),
            }

        if trend:
            trend_dir = str(trend.get("direction", "neutral"))
            result["agents"]["trend"] = {
                "direction": trend_dir,
                "structure": trend.get("structure_status", ""),
                "approved": trend_dir not in ("neutral", "sideways"),
            }

        if vol:
            result["agents"]["volatility"] = {
                "atr": float(vol.get("atr_value") or 0.0),
                "rsi": float(vol.get("rsi") or 0.0),
                "approved": bool(vol.get("setup_allowed", False)),
            }

        level = agent_scores.get("level") or {}
        if level:
            nearest = level.get("nearest_level") or {}
            result["agents"]["level"] = {
                "zone_high": float(nearest.get("zone_high") or nearest.get("high") or 0.0),
                "zone_low": float(nearest.get("zone_low") or nearest.get("low") or 0.0),
                "atr_distance": float(agent_scores.get("_atr_distance") or 0.0),
                "approved": bool(nearest),
            }

        if entry:
            result["agents"]["entry"] = {
                "type": entry.get("entry_type", ""),
                "trigger_price": float(entry.get("entry_price") or 0.0),
            }

        if risk:
            result["agents"]["risk"] = {
                "sl": float(risk.get("stop_loss") or 0.0),
                "tp": float(risk.get("take_profit") or 0.0),
                "crv": float(risk.get("crv") or 0.0),
                "approved": bool(risk.get("trade_allowed", False)),
            }

        if validation:
            result["agents"]["validation"] = {
                "confidence": float(validation.get("confidence_score") or 0.0),
                "approved": bool(validation.get("validated", False)),
            }

        # Bei Ablehnung: Ablehnungsgrund eintragen
        if signal.status.value.lower() == "rejected":
            rejection_agent, rejection_reason = self._find_rejection_point(agent_scores)
            if rejection_agent:
                result["rejection_agent"] = rejection_agent
                result["rejection_reason"] = rejection_reason

        return result

    def _find_rejection_point(self, agent_scores: dict) -> tuple[str, str]:
        """Bestimmt welcher Agent das Signal abgelehnt hat."""
        macro = agent_scores.get("macro") or {}
        if not macro.get("trading_allowed", True):
            return "macro", macro.get("rejection_reason", "Makro-Freigabe verweigert")

        trend = agent_scores.get("trend") or {}
        trend_dir = str(trend.get("direction", "neutral"))
        if trend_dir in ("neutral", "sideways"):
            return "trend", f"Kein klarer Trend (direction={trend_dir})"

        vol = agent_scores.get("vol") or {}
        if vol and not vol.get("setup_allowed", True):
            return "volatility", vol.get("rejection_reason", "Volatilitäts-Freigabe verweigert")

        risk = agent_scores.get("risk") or {}
        if risk and not risk.get("trade_allowed", True):
            return "risk", risk.get("rejection_reason", "Risk-Gate abgelehnt")

        return "", ""

    def _build_entry_trigger_hint(self, entry_result: dict, signal: Signal) -> str:
        """Erstellt einen lesbaren Hinweis worauf beim Entry gewartet wird."""
        entry_type = entry_result.get("entry_type", "")
        price = signal.entry_price
        inst = signal.instrument

        # Preisformatierung – JPY 3 Dezimalstellen, Gold 2, sonst 5
        if "JPY" in inst.upper():
            price_str = f"{price:.3f}"
        elif any(x in inst.upper() for x in ("XAU", "XAG", "GOLD")):
            price_str = f"{price:.2f}"
        elif price >= 1000:
            price_str = f"{price:.2f}"
        else:
            price_str = f"{price:.5f}"

        hints = {
            "rejection": f"Warte auf Rejection-Wick bei {price_str}",
            "pullback": "Warte auf Pullback zu EMA21",
            "breakout": f"Warte auf Breakout-Retest bei {price_str}",
            "market": "Market-Order bereit",
        }
        return hints.get(entry_type, f"Warte auf Entry-Trigger bei {price_str}")

    def _get_active_trade_dicts(self) -> list[dict]:
        """Liest offene DB-Trades und konvertiert sie zu Display-Dicts."""
        try:
            open_trades = self.db.get_open_trades()
            result = []
            for trade in open_trades:
                result.append({
                    "instrument": trade.get("instrument", ""),
                    "direction": trade.get("direction", ""),
                    "entry_price": float(trade.get("entry_price") or 0.0),
                    "stop_loss": float(trade.get("sl") or 0.0),
                    "take_profit": float(trade.get("tp") or 0.0),
                    "lot_size": float(trade.get("lot_size") or 0.0),
                    "confidence_score": 0.0,
                    "crv": 0.0,
                    "timestamp": str(trade.get("open_time") or ""),
                    "zone_status": "active_trade",
                    "mt5_ticket": trade.get("mt5_ticket"),
                })
            return result
        except Exception as e:
            logger.debug(f"_get_active_trade_dicts Fehler: {e}")
            return []

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
