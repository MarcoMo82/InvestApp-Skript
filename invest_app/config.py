"""
Zentrale Konfiguration für das InvestApp Trading-System.
Lädt alle Einstellungen aus config.json, Secrets (API-Keys, Passwörter) aus .env.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# Keys die nie in config.json geschrieben werden (kommen aus .env)
_SECRET_KEYS = {"anthropic_api_key", "openai_api_key", "mt5_login", "mt5_password"}

# Keys die als Path-Objekte geliefert werden (werden im JSON als Strings gespeichert)
_PATH_KEYS = {"db_path", "log_dir", "output_dir"}

# Gruppenstruktur für config.json – definiert Reihenfolge und Zugehörigkeit
_SECTIONS: dict[str, list[str]] = {
    "symbols": [
        "fallback_symbols", "yfinance_symbol_map",
        "scanner_enabled", "scanner_max_symbols", "scanner_min_score", "scanner_top_n",
        "scanner_respect_category_limits", "scanner_interval_minutes",
        "scanner_categories", "scanner_category_limits",
        "symbol_provider_max_file_age_minutes",
    ],
    "risk": [
        "risk_per_trade", "max_daily_loss", "max_open_positions", "min_crv",
        "atr_period", "atr_sl_multiplier", "atr_tp_multiplier", "min_confidence_score",
        "spread_filter_multiplier", "normal_spread_pips", "drawdown_enabled",
    ],
    "sessions": [
        "london_open_hour", "london_close_hour", "ny_open_hour", "ny_close_hour",
        "asian_open_hour", "asian_close_hour",
        "asian_session_trend_block", "asian_session_start_utc", "asian_session_end_utc",
        "session_scoring_enabled", "session_overlap_bonus", "session_solo_bonus",
    ],
    "correlation": [
        "correlation_check_enabled",
    ],
    "smc": [
        "fvg_enabled", "fvg_confidence_bonus",
        "ob_enabled", "ob_confidence_bonus", "ob_tolerance_pips",
        "smc_triple_confluence_enabled", "smc_triple_bonus", "smc_double_bonus",
    ],
    "safe_haven": [
        "safe_haven_enabled", "vix_risk_off_threshold", "safe_haven_confidence_bonus",
    ],
    "pipeline": [
        "cycle_interval_minutes", "watch_interval_seconds", "news_cache_ttl",
        "confidence_threshold", "news_yahoo_enabled", "news_block_enabled", "news_block_minutes_before", "news_block_minutes_after",
        "simulation_mode_enabled",
        "simulation_trigger_after_watch_cycles", "simulation_symbol",
        "simulation_direction", "simulation_lot_size", "startup_analysis_enabled",
    ],
    "mt5": [
        "mt5_server", "mt5_common_files_path", "mt5_symbols_file", "mt5_order_file",
        "mt5_result_file", "mt5_zones_file", "mt5_zones_export_enabled", "mt5_path",
    ],
    "chart": [
        "htf_timeframe", "entry_timeframe", "htf_bars", "entry_bars",
        "chart_entry_tolerance_pct", "ema_periods",
    ],
    "chart_colors": [
        "chart_color_entry_long", "chart_color_entry_short", "chart_color_sl",
        "chart_color_tp", "chart_color_order_block_bull", "chart_color_order_block_bear",
        "chart_color_psych_level", "chart_color_key_level_support",
        "chart_color_key_level_resistance", "chart_color_fvg", "chart_color_liquidity",
        "chart_line_width_main", "chart_line_width_secondary",
    ],
    "watch_agent": [
        "watch_agent_zone_update_enabled", "watch_agent_zone_update_entry_tolerance_pct",
        "watch_agent_zone_update_ob_consumed_threshold", "watch_agent_heartbeat_interval",
    ],
    "model": [
        "claude_model", "claude_max_tokens", "claude_retry_attempts", "claude_retry_delay",
        "openai_model", "openai_temperature", "openai_max_tokens",
    ],
    "app": [
        "trading_mode", "log_level", "log_dir", "output_dir", "db_path",
        "show_startup_banner", "show_cycle_banner",
    ],
}


class Config:
    """
    Lädt Konfiguration aus config.json.
    Fehlende Keys werden automatisch mit Defaults ergänzt und zurückgeschrieben.
    Secrets kommen ausschließlich aus .env (nie aus config.json).
    """

    DEFAULTS: dict = {
        # symbols
        "fallback_symbols": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "XAUUSD", "BTCUSD"],
        "yfinance_symbol_map": {
            "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
            "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
            "USDJPY": "USDJPY=X", "USDCHF": "USDCHF=X",
            "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
            "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X",
            "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
            "XAUUSD": "GC=F",
        },
        "scanner_enabled": True,
        "scanner_max_symbols": 10,
        "scanner_min_score": 10,
        "scanner_top_n": 5,
        "scanner_respect_category_limits": True,
        "scanner_interval_minutes": 60,
        "scanner_categories": ["forex", "indices", "commodities"],
        "scanner_category_limits": {"forex": 5, "indices": 3, "commodities": 2, "crypto": 0},
        "symbol_provider_max_file_age_minutes": 5,
        # risk
        "drawdown_enabled": True,
        "risk_per_trade": 0.01,
        "max_daily_loss": 0.03,
        "max_open_positions": 3,
        "min_crv": 2.0,
        "atr_period": 14,
        "atr_sl_multiplier": 2.0,
        "atr_tp_multiplier": 4.0,
        "min_confidence_score": 80.0,
        "spread_filter_multiplier": 3.0,
        "normal_spread_pips": {
            "EURUSD": 0.5, "GBPUSD": 1.0, "USDJPY": 0.5, "USDCHF": 1.0,
            "AUDUSD": 0.8, "USDCAD": 1.0, "NZDUSD": 1.0, "GBPJPY": 1.5,
            "EURJPY": 0.8, "EURGBP": 0.7, "XAUUSD": 3.0, "BTCUSD": 50.0,
        },
        # sessions
        "london_open_hour": 8,
        "london_close_hour": 17,
        "ny_open_hour": 13,
        "ny_close_hour": 22,
        "asian_open_hour": 0,
        "asian_close_hour": 8,
        # P2.2 – Asian Session Trend-Block
        "asian_session_trend_block": True,
        "asian_session_start_utc": 0,
        "asian_session_end_utc": 9,
        # P2.4 – Session Scoring
        "session_scoring_enabled": True,
        "session_overlap_bonus": 5,
        "session_solo_bonus": 2,
        # P3.x – SMC Entry-Logik
        "fvg_enabled": True,
        "fvg_confidence_bonus": 10,
        "ob_enabled": True,
        "ob_confidence_bonus": 15,
        "ob_tolerance_pips": 5.0,
        "smc_triple_confluence_enabled": True,
        "smc_triple_bonus": 20,
        "smc_double_bonus": 10,
        # P2.1 – Korrelations-Check
        "correlation_check_enabled": True,
        # P1.4 – News-Block
        "news_block_enabled": True,
        "news_block_minutes_before": 30,
        "news_block_minutes_after": 30,
        # P2.3 – Safe-Haven
        "safe_haven_enabled": True,
        "vix_risk_off_threshold": 20,
        "safe_haven_confidence_bonus": 10,
        # pipeline
        "cycle_interval_minutes": 5,
        "watch_interval_seconds": 60,
        "news_cache_ttl": 3600,
        "confidence_threshold": 80,
        "news_yahoo_enabled": False,
        "news_block_enabled": True,
        "news_block_minutes_before": 30,
        "news_block_minutes_after": 30,
        "simulation_mode_enabled": False,
        "simulation_trigger_after_watch_cycles": 3,
        "simulation_symbol": "EURUSD",
        "simulation_direction": "long",
        "simulation_lot_size": 0.01,
        "startup_analysis_enabled": True,
        # mt5
        "mt5_server": "",
        "mt5_common_files_path": "",
        "mt5_symbols_file": "available_symbols.json",
        "mt5_order_file": "pending_order.json",
        "mt5_result_file": "order_result.json",
        "mt5_zones_file": "mt5_zones.json",
        "mt5_zones_export_enabled": True,
        "mt5_path": r"C:\Program Files\MetaTrader 5\terminal64.exe",
        # chart
        "htf_timeframe": "15m",
        "entry_timeframe": "5m",
        "htf_bars": 200,
        "entry_bars": 100,
        "chart_entry_tolerance_pct": 0.05,
        "ema_periods": [9, 21, 50, 200],
        # chart_colors
        "chart_color_entry_long": 33023,
        "chart_color_entry_short": 255,
        "chart_color_sl": 255,
        "chart_color_tp": 65280,
        "chart_color_order_block_bull": 16776960,
        "chart_color_order_block_bear": 16744272,
        "chart_color_psych_level": 8421504,
        "chart_color_key_level_support": 65280,
        "chart_color_key_level_resistance": 255,
        "chart_color_fvg": 5087744,
        "chart_color_liquidity": 10235616,
        "chart_line_width_main": 2,
        "chart_line_width_secondary": 1,
        # watch_agent
        "watch_agent_zone_update_enabled": True,
        "watch_agent_zone_update_entry_tolerance_pct": 0.5,
        "watch_agent_zone_update_ob_consumed_threshold": 0.3,
        "watch_agent_heartbeat_interval": 5,
        # model
        "claude_model": "claude-opus-4-6",
        "claude_max_tokens": 2048,
        "claude_retry_attempts": 3,
        "claude_retry_delay": 2.0,
        "openai_model": "gpt-4o",
        "openai_temperature": 0.2,
        "openai_max_tokens": 2000,
        # app
        "trading_mode": "demo",
        "log_level": "INFO",
        "log_dir": "logs",
        "output_dir": "Output",
        "db_path": "invest_app.db",
        "show_startup_banner": True,
        "show_cycle_banner": True,
    }

    def __init__(self, config_path: Path = CONFIG_PATH):
        self._path = config_path
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            with open(self._path, encoding="utf-8") as f:
                raw = json.load(f)
            flat: dict = {}
            for key, val in raw.items():
                if key.startswith("_"):
                    continue
                if isinstance(val, dict):
                    # Section-Dict: Inhalte flach übernehmen
                    # (dict-Werte wie normal_spread_pips bleiben als dict erhalten)
                    for k, v in val.items():
                        flat[k] = v
                else:
                    flat[key] = val
        else:
            flat = {}

        # Fehlende Keys mit Defaults ergänzen
        changed = not self._path.exists()
        for key, default in self.DEFAULTS.items():
            if key not in flat:
                flat[key] = default
                changed = True

        # Path-Keys als Path-Objekte relativ zum Config-Verzeichnis
        base = self._path.parent
        flat["db_path"] = base / str(flat.get("db_path", "invest_app.db"))
        flat["log_dir"] = base / str(flat.get("log_dir", "logs"))
        flat["output_dir"] = base / str(flat.get("output_dir", "Output"))

        self._data = flat

        # Secrets aus .env – niemals aus config.json lesen oder dorthin schreiben
        self._data["anthropic_api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
        self._data["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
        self._data["mt5_login"] = int(os.getenv("MT5_LOGIN", "0") or "0")
        self._data["mt5_password"] = os.getenv("MT5_PASSWORD", "")
        # MT5_SERVER aus .env überschreibt config.json (ist ein Secret)
        env_server = os.getenv("MT5_SERVER", "")
        if env_server:
            self._data["mt5_server"] = env_server

        # Verzeichnisse anlegen
        self._data["log_dir"].mkdir(exist_ok=True)
        self._data["output_dir"].mkdir(exist_ok=True)

        # Auto-Migration: neue Keys in config.json nachschreiben
        if changed:
            self._save()

    def _save(self) -> None:
        """Schreibt alle nicht-Secret Parameter gruppiert zurück nach config.json."""
        output: dict = {
            "_comment": "InvestApp Konfiguration – alle Parameter hier editierbar. Secrets (API-Keys, Passwörter) bleiben in .env",
            "_version": "1.0",
        }

        # Werte vorbereiten: Path → str (relativ), Secrets ausschließen
        values: dict = {}
        for k, v in self._data.items():
            if k in _SECRET_KEYS:
                continue
            if isinstance(v, Path):
                try:
                    values[k] = str(v.relative_to(self._path.parent))
                except ValueError:
                    values[k] = str(v)
            else:
                values[k] = v

        # Gruppiert in Sections schreiben
        written_keys: set = set()
        for section, keys in _SECTIONS.items():
            section_dict: dict = {}
            for key in keys:
                if key in values:
                    section_dict[key] = values[key]
                    written_keys.add(key)
            if section_dict:
                output[section] = section_dict

        # Verbleibende Keys (nicht in _SECTIONS) in "other" schreiben
        other: dict = {k: v for k, v in values.items() if k not in written_keys}
        if other:
            output["other"] = other

        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"Config hat keinen Parameter '{name}'")

    @property
    def all_symbols(self) -> list[str]:
        # Rückwärtskompatibilität: gibt fallback_symbols zurück
        return self._data.get("fallback_symbols", self._data.get("all_symbols", []))

    @property
    def is_live(self) -> bool:
        return self._data.get("trading_mode", "demo").lower() == "live"


# Singleton-Instanz
config = Config()
