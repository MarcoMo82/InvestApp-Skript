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
            )
            if connector.connect():
                logger.info("MT5-Connector aktiv.")
                return connector
            else:
                logger.warning("MT5-Verbindung fehlgeschlagen – Fallback auf yfinance.")
        except Exception as e:
            logger.warning(f"MT5-Connector Fehler: {e} – Fallback auf yfinance.")

    logger.info("yfinance-Connector aktiv (kein Order-Execution).")
    connector = YFinanceConnector(symbol_map=config.yfinance_symbol_map)
    connector.connect()
    return connector


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

    learning_agent = LearningAgent(output_dir=config.output_dir, db=db, config=config)

    return Orchestrator(
        config=config,
        connector=connector,
        macro_agent=MacroAgent(claude_client=claude, news_fetcher=news),
        trend_agent=TrendAgent(ema_periods=config.ema_periods),
        volatility_agent=VolatilityAgent(atr_period=config.atr_period),
        level_agent=LevelAgent(),
        entry_agent=EntryAgent(),
        risk_agent=RiskAgent(
            sl_atr_multiplier=config.atr_sl_multiplier,
            min_crv=config.min_crv,
            risk_per_trade=config.risk_per_trade,
        ),
        validation_agent=ValidationAgent(claude_client=claude),
        reporting_agent=ReportingAgent(output_dir=config.output_dir),
        database=db,
        learning_agent=learning_agent,
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
