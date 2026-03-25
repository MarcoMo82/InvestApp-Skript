"""
InvestApp – Einstiegspunkt.
Initialisiert alle Komponenten und startet die Trading-Pipeline.
"""

from __future__ import annotations

import signal
import sys
import time

from config import config
from utils.logger import get_logger, setup_root_logger
from utils.database import Database
from utils.claude_client import ClaudeClient
from data.news_fetcher import NewsFetcher

setup_root_logger(config.log_dir, config.log_level)
logger = get_logger(__name__)


def startup_initialization(config, symbols_list: list) -> None:
    """Gibt ein formatiertes Startup-Banner in der Konsole aus."""
    import time as _time
    t0 = _time.time()
    print("=" * 60)
    print("  InvestApp — KI Trading System wird gestartet")
    print("=" * 60)
    print(f"[INIT] 1/4 | Konfiguration...            OK")
    print(f"[INIT] 2/4 | Agenten bereit...            OK")
    print(f"[INIT] 3/4 | Symbole geladen...           {len(symbols_list)} aktiv")
    print(f"[INIT] 4/4 | System bereit")
    elapsed = _time.time() - t0
    sym_preview = ", ".join(symbols_list[:5]) + ("..." if len(symbols_list) > 5 else "")
    print("=" * 60)
    print(f"  Start in {elapsed:.1f}s | Symbole: {sym_preview}")
    print(f"  Analyse alle {config.cycle_interval_minutes} Min | Watch-Agent: 1-Min-Takt")
    print("=" * 60)


def build_connector():
    """
    Versucht MT5 zu verbinden. Fällt auf yfinance zurück wenn MT5 nicht verfügbar.
    """
    from data.mt5_connector import MT5_AVAILABLE, MT5Connector
    from data.yfinance_connector import YFinanceConnector

    if MT5_AVAILABLE and config.mt5_login:
        try:
            connector = MT5Connector(
                login=config.mt5_login,
                password=config.mt5_password,
                server=config.mt5_server,
                path=config.mt5_path,
                config=config,
            )
            if connector.connect():
                logger.info("MT5-Connector aktiv.")
                connector.diagnose()
                return connector
            else:
                logger.warning("MT5-Verbindung fehlgeschlagen – Fallback auf yfinance.")
        except Exception as e:
            logger.warning(f"MT5-Connector Fehler: {e} – Fallback auf yfinance.")

    logger.info("yfinance-Connector aktiv (kein Order-Execution).")
    connector = YFinanceConnector(symbol_map=config.yfinance_symbol_map)
    connector.connect()
    return connector


def build_scanner(connector):
    """Baut den ScannerAgent auf wenn aktiviert."""
    if not config.scanner_enabled:
        return None
    from agents.scanner_agent import ScannerAgent
    return ScannerAgent(config=config, connector=connector)


def build_orchestrator(connector, db: Database, claude: ClaudeClient, news: NewsFetcher):
    """Baut die vollständige Agent-Pipeline auf."""
    from agents.orchestrator import Orchestrator
    from agents.macro_agent import MacroAgent
    from agents.trend_agent import TrendAgent
    from agents.volatility_agent import VolatilityAgent
    from agents.level_agent import LevelAgent
    from agents.entry_agent import EntryAgent
    from agents.risk_agent import RiskAgent
    from agents.validation_agent import ValidationAgent
    from agents.reporting_agent import ReportingAgent
    from agents.learning_agent import LearningAgent
    from agents.watch_agent import WatchAgent
    from agents.chart_exporter import ChartExporter

    learning_agent = LearningAgent(output_dir=config.output_dir, db=db, config=config)

    chart_exporter = ChartExporter(config=config)

    # Simulation Agent (optional, nur wenn aktiviert)
    simulation_agent = None
    if config.simulation_mode_enabled:
        from agents.simulation_agent import SimulationAgent
        simulation_agent = SimulationAgent(config=config, connector=connector)
        logger.info(
            "[Simulation] Test-Modus aktiviert — startet nach Watch-Zyklus "
            f"{config.simulation_trigger_after_watch_cycles}"
        )

    watch_agent = WatchAgent(
        connector=connector,
        db=db,
        config=config,
        simulation_agent=simulation_agent,
        chart_exporter=chart_exporter,
    )

    agents = [
        MacroAgent(claude_client=claude, news_fetcher=news),
        TrendAgent(ema_periods=config.ema_periods),
        VolatilityAgent(atr_period=config.atr_period),
        LevelAgent(),
        EntryAgent(config=config),
        RiskAgent(
            sl_atr_multiplier=config.atr_sl_multiplier,
            min_crv=config.min_crv,
            risk_per_trade=config.risk_per_trade,
            config=config,
        ),
        ValidationAgent(claude_client=claude),
        ReportingAgent(output_dir=config.output_dir),
    ]
    # DB-Referenz an alle Agenten übergeben (für Agent-Logging)
    for agent in agents:
        agent.db = db

    macro, trend, volatility, level, entry, risk, validation, reporting = agents

    return Orchestrator(
        config=config,
        connector=connector,
        macro_agent=macro,
        trend_agent=trend,
        volatility_agent=volatility,
        level_agent=level,
        entry_agent=entry,
        risk_agent=risk,
        validation_agent=validation,
        reporting_agent=reporting,
        database=db,
        learning_agent=learning_agent,
        watch_agent=watch_agent,
        chart_exporter=chart_exporter,
        scanner_agent=build_scanner(connector),
    )


def main() -> None:
    logger.info("=" * 60)
    logger.info("InvestApp Trading-System startet")
    logger.info(f"Modus: {config.trading_mode.upper()}")
    logger.info(f"Symbole: {len(config.all_symbols)}")
    logger.info(f"Zyklus: alle {config.cycle_interval_minutes} Minuten")
    logger.info("=" * 60)

    # Datenbank initialisieren
    db = Database(config.db_path)

    # Claude-Client initialisieren
    claude = ClaudeClient(
        api_key=config.anthropic_api_key,
        model=config.claude_model,
        max_tokens=config.claude_max_tokens,
        retry_attempts=config.claude_retry_attempts,
        retry_delay=config.claude_retry_delay,
    )

    # News-Fetcher
    news = NewsFetcher()

    # Connector aufbauen (MT5 oder yfinance)
    connector = build_connector()

    # Orchestrator aufbauen
    orchestrator = build_orchestrator(connector, db, claude, news)

    # Graceful Shutdown via SIGINT / SIGTERM
    def shutdown(signum, frame):
        logger.info("Shutdown-Signal empfangen – beende sauber...")
        orchestrator.stop_scheduler()
        connector.disconnect()
        logger.info("InvestApp beendet.")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Initialen Scanner-Lauf: MT5-Symbole laden und active_symbols setzen
    orchestrator._run_scanner()

    # Startup-Banner
    active = orchestrator.active_symbols or config.all_symbols
    if getattr(config, "show_startup_banner", True):
        startup_initialization(config, active)

    # Ersten Zyklus sofort ausführen
    logger.info("Starte ersten Analyse-Zyklus...")
    orchestrator.run_cycle()

    # Scheduler für automatische Zyklen starten
    orchestrator.start_scheduler()

    logger.info("InvestApp läuft. Strg+C zum Beenden.")

    # Hauptthread am Leben halten
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
