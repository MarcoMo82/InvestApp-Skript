"""
Orchestrator: Hauptsteuerung der Agent-Pipeline.
Führt alle Agenten sequenziell aus und aggregiert die Ergebnisse zu einem Signal.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .macro_agent import MacroAgent
from .trend_agent import TrendAgent
from .volatility_agent import VolatilityAgent
from .level_agent import LevelAgent
from .entry_agent import EntryAgent
from .risk_agent import RiskAgent
from .validation_agent import ValidationAgent
from .reporting_agent import ReportingAgent
from models.signal import Signal, SignalStatus, Direction
from utils.logger import get_logger
from utils.database import Database

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
        if self._check_daily_loss_limit():
            logger.warning("Daily-Loss-Limit erreicht – Zyklus übersprungen.")
            return []

        self._cycle_count += 1
        cycle_id = f"cycle_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{self._cycle_count}"
        logger.info(f"=== Zyklus {self._cycle_count} gestartet ({cycle_id}) ===")

        all_signals: list[Signal] = []
        symbols = self.config.all_symbols

        for symbol in symbols:
            try:
                signal = self._analyze_symbol(symbol)
                if signal:
                    all_signals.append(signal)
                    self.db.save_signal(signal)
            except Exception as e:
                logger.error(f"Fehler bei {symbol}: {e}", exc_info=True)

        # Reporting
        if all_signals:
            self.reporting_agent.run({"signals": all_signals, "cycle_id": cycle_id})

        approved = [s for s in all_signals if s.status == SignalStatus.APPROVED]
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
        if direction == "neutral":
            logger.debug(f"{symbol}: Kein klarer Trend")
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
        """Startet den APScheduler für automatische Zyklen alle 15 Minuten."""
        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(
            func=self.run_cycle,
            trigger=IntervalTrigger(minutes=self.config.cycle_interval_minutes),
            id="main_cycle",
            name="InvestApp Hauptzyklus",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            f"Scheduler gestartet – Zyklus alle {self.config.cycle_interval_minutes} Minuten."
        )

    def stop_scheduler(self) -> None:
        """Stoppt den Scheduler sauber."""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=True)
            logger.info("Scheduler gestoppt.")

    def activate_kill_switch(self) -> None:
        """Aktiviert den Kill-Switch – unterbricht alle weiteren Zyklen."""
        self._kill_switch.set()
        logger.warning("KILL-SWITCH AKTIVIERT – keine weiteren Zyklen.")

    def deactivate_kill_switch(self) -> None:
        """Deaktiviert den Kill-Switch."""
        self._kill_switch.clear()
        logger.info("Kill-Switch deaktiviert.")

    def _check_daily_loss_limit(self) -> bool:
        """Prüft ob das tägliche Verlustlimit erreicht wurde."""
        try:
            daily_pnl = self.db.get_daily_pnl()
            balance = self.connector.get_account_balance()
            max_loss = balance * self.config.max_daily_loss

            if daily_pnl < -max_loss:
                logger.warning(
                    f"Daily-Loss-Limit erreicht: {daily_pnl:.2f} / Limit: -{max_loss:.2f}"
                )
                return True
        except Exception as e:
            logger.error(f"Daily-Loss-Check fehlgeschlagen: {e}")
        return False
