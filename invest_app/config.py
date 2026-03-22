"""
Zentrale Konfiguration für das InvestApp Trading-System.
Lädt alle Einstellungen aus der .env-Datei und stellt sie typisiert bereit.
"""

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
        default_factory=lambda: float(os.getenv("MAX_DAILY_LOSS", "0.03"))
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
    cycle_interval_minutes: int = 15

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
