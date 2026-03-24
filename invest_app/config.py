"""
Zentrale Konfiguration für das InvestApp Trading-System.
Lädt alle Einstellungen aus der .env-Datei und stellt sie typisiert bereit.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent


@dataclass
class Config:
    # --- API & Verbindung ---
    anthropic_api_key: str = field(default_factory=lambda: os.environ["ANTHROPIC_API_KEY"])
    mt5_login: int = field(default_factory=lambda: int(os.getenv("MT5_LOGIN", "0")))
    mt5_password: str = field(default_factory=lambda: os.getenv("MT5_PASSWORD", ""))
    mt5_server: str = field(default_factory=lambda: os.getenv("MT5_SERVER", ""))
    mt5_path: str = field(
        default_factory=lambda: os.getenv(
            "MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"
        )
    )

    # --- Trading-Modus ---
    trading_mode: str = field(default_factory=lambda: os.getenv("TRADING_MODE", "demo"))

    # --- Risiko-Parameter ---
    risk_per_trade: float = field(
        default_factory=lambda: float(os.getenv("RISK_PER_TRADE", "0.01"))
    )
    max_daily_loss: float = field(
        default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS", "0.05"))
    )
    max_open_positions: int = field(
        default_factory=lambda: int(os.getenv("MAX_OPEN_POSITIONS", "3"))
    )

    # --- Spread-Filter ---
    normal_spread_pips: dict = field(default_factory=lambda: json.loads(
        os.getenv("NORMAL_SPREAD_PIPS", json.dumps({
            "EURUSD": 0.5, "GBPUSD": 1.0, "USDJPY": 0.5, "USDCHF": 1.0,
            "AUDUSD": 0.8, "USDCAD": 1.0, "NZDUSD": 1.0, "GBPJPY": 1.5,
            "EURJPY": 0.8, "EURGBP": 0.7, "XAUUSD": 3.0, "BTCUSD": 50.0,
        }))
    ))
    spread_filter_multiplier: float = field(
        default_factory=lambda: float(os.getenv("SPREAD_FILTER_MULTIPLIER", "3.0"))
    )

    # --- Signal-Qualität ---
    min_confidence_score: float = 80.0  # Signals unter diesem Wert werden verworfen
    min_crv: float = 2.0                # Mindestkurs-Risiko-Verhältnis

    # --- ATR-Parameter ---
    atr_period: int = 14
    atr_sl_multiplier: float = 2.0      # SL = ATR * Multiplier
    atr_tp_multiplier: float = 4.0      # TP = ATR * Multiplier (ergibt CRV 1:2)

    # --- Zeitrahmen ---
    htf_timeframe: str = "15m"          # Higher Timeframe für Trend
    entry_timeframe: str = "5m"         # Entry-Zeitrahmen
    htf_bars: int = 200                 # Anzahl Bars für HTF-Analyse
    entry_bars: int = 100               # Anzahl Bars für Entry-Analyse

    # --- EMA-Parameter ---
    ema_periods: list = field(default_factory=lambda: [9, 21, 50, 200])

    # --- Symbole / Märkte ---
    forex_symbols: list = field(default_factory=lambda: [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
        "EURGBP", "EURJPY", "GBPJPY",
    ])
    stock_symbols: list = field(default_factory=lambda: [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META",
    ])
    crypto_symbols: list = field(default_factory=lambda: [
        "BTCUSD", "ETHUSD",
    ])

    # yfinance-Symbole (abweichende Namensgebung)
    yfinance_symbol_map: dict = field(default_factory=lambda: {
        "BTCUSD": "BTC-USD",
        "ETHUSD": "ETH-USD",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "USDCHF": "USDCHF=X",
        "AUDUSD": "AUDUSD=X",
        "USDCAD": "USDCAD=X",
        "NZDUSD": "NZDUSD=X",
        "EURGBP": "EURGBP=X",
        "EURJPY": "EURJPY=X",
        "GBPJPY": "GBPJPY=X",
    })

    # --- Trading-Sessions ---
    london_open_hour: int = 8    # UTC
    london_close_hour: int = 17  # UTC
    ny_open_hour: int = 13       # UTC
    ny_close_hour: int = 22      # UTC

    # --- Scheduler ---
    cycle_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("CYCLE_INTERVAL_MINUTES", "5"))
    )
    news_cache_ttl: int = field(default_factory=lambda: int(os.getenv("NEWS_CACHE_TTL", "3600")))  # 60 Minuten

    # --- Claude-Modell ---
    claude_model: str = "claude-opus-4-6"
    claude_max_tokens: int = 2048
    claude_retry_attempts: int = 3
    claude_retry_delay: float = 2.0  # Sekunden zwischen Retries

    # --- Pfade ---
    db_path: Path = field(default_factory=lambda: BASE_DIR / "invest_app.db")
    log_dir: Path = field(default_factory=lambda: BASE_DIR / "logs")
    output_dir: Path = field(default_factory=lambda: BASE_DIR / "Output")
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # --- MT5 Order-Datei-Protokoll ---
    mt5_common_files_path: str = ""  # Leer = Output/ verwenden; sonst MT5 Common Files Pfad

    # --- Chart Export (MT5-Visualisierung) ---
    mt5_zones_file: str = field(
        default_factory=lambda: os.getenv("MT5_ZONES_FILE", "Output/mt5_zones.json")
    )
    mt5_zones_export_enabled: bool = field(
        default_factory=lambda: os.getenv("MT5_ZONES_EXPORT_ENABLED", "true").lower() == "true"
    )

    # --- News-Quellen ---
    news_yahoo_enabled: bool = field(
        default_factory=lambda: os.getenv("NEWS_YAHOO_ENABLED", "False").lower() == "true"
    )

    # --- Test-Modus (Simulation) ---
    simulation_mode_enabled: bool = field(
        default_factory=lambda: os.getenv("SIMULATION_MODE_ENABLED", "False").lower() == "true"
    )
    simulation_trigger_after_watch_cycles: int = field(
        default_factory=lambda: int(os.getenv("SIMULATION_TRIGGER_AFTER_WATCH_CYCLES", "3"))
    )
    simulation_symbol: str = field(
        default_factory=lambda: os.getenv("SIMULATION_SYMBOL", "EURUSD")
    )
    simulation_direction: str = field(
        default_factory=lambda: os.getenv("SIMULATION_DIRECTION", "long")
    )
    simulation_lot_size: float = field(
        default_factory=lambda: float(os.getenv("SIMULATION_LOT_SIZE", "0.01"))
    )

    # --- Konsolen-Ausgabe ---
    show_startup_banner: bool = True
    show_cycle_banner: bool = True
    watch_agent_heartbeat_interval: int = 5  # alle N Watch-Zyklen
    startup_analysis_enabled: bool = True    # Sofort-Analyse beim Start

    # --- Scanner ---
    scanner_enabled: bool = field(
        default_factory=lambda: os.getenv("SCANNER_ENABLED", "True").lower() == "true"
    )
    scanner_max_symbols: int = field(
        default_factory=lambda: int(os.getenv("SCANNER_MAX_SYMBOLS", "10"))
    )
    scanner_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("SCANNER_INTERVAL_MINUTES", "60"))
    )
    scanner_categories: list = field(
        default_factory=lambda: ["forex", "indices", "commodities"]
    )
    scanner_category_limits: dict = field(
        default_factory=lambda: {"forex": 5, "indices": 3, "commodities": 2, "crypto": 0}
    )

    # Entry-Toleranz für die Zonenberechnung (Prozent vom Preis)
    chart_entry_tolerance_pct: float = 0.05

    # --- Watch-Agent: Zone-Update ---
    watch_agent_zone_update_enabled: bool = field(
        default_factory=lambda: os.getenv("WATCH_AGENT_ZONE_UPDATE_ENABLED", "True") == "True"
    )
    watch_agent_zone_update_entry_tolerance_pct: float = field(
        default_factory=lambda: float(os.getenv("WATCH_AGENT_ZONE_UPDATE_ENTRY_TOLERANCE_PCT", "0.5"))
    )
    # Order Block gilt als konsumiert wenn Kurs > 0.3 ATR tief eingedrungen ist
    watch_agent_zone_update_ob_consumed_threshold: float = field(
        default_factory=lambda: float(os.getenv("WATCH_AGENT_ZONE_UPDATE_OB_CONSUMED_THRESHOLD", "0.3"))
    )

    # Farben als MQL5 Color-Codes (int, BGR-Format)
    chart_color_entry_long: int = 33023           # blau
    chart_color_entry_short: int = 255            # rot
    chart_color_sl: int = 255                     # rot
    chart_color_tp: int = 65280                   # grün
    chart_color_order_block_bull: int = 16776960  # gelb
    chart_color_order_block_bear: int = 16744272  # orange
    chart_color_psych_level: int = 8421504        # grau
    chart_color_key_level_support: int = 65280    # grün
    chart_color_key_level_resistance: int = 255   # rot

    # Linienbreiten
    chart_line_width_main: int = 2
    chart_line_width_secondary: int = 1

    def __post_init__(self) -> None:
        self.log_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)

    @property
    def all_symbols(self) -> list[str]:
        return self.forex_symbols + self.stock_symbols + self.crypto_symbols

    @property
    def is_live(self) -> bool:
        return self.trading_mode.lower() == "live"


# Singleton-Instanz
config = Config()
