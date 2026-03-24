"""
yfinance Fallback-Connector – identische Schnittstelle wie MT5Connector.
Wird verwendet wenn MT5 nicht verfügbar ist (Linux, Mac, Demo ohne Terminal).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

from utils.logger import get_logger

logger = get_logger(__name__)

# Mapping: MT5-Symbol → yfinance-Ticker
SYMBOL_MAP: dict[str, str] = {
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
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}

# Zeitrahmen-Mapping: String → yfinance interval
TIMEFRAME_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Perioden für yfinance (abhängig vom Zeitrahmen)
PERIOD_MAP: dict[str, str] = {
    "1m": "1d",
    "5m": "5d",
    "15m": "5d",
    "30m": "10d",
    "1h": "60d",
    "4h": "60d",
    "1d": "1y",
}


class YFinanceConnector:
    """
    yfinance-basierter Daten-Connector als Drop-in-Ersatz für MT5Connector.
    Order-Execution ist NICHT verfügbar (Paper-Trading-Modus).
    """

    def __init__(self, symbol_map: Optional[dict[str, str]] = None) -> None:
        self._symbol_map = symbol_map or SYMBOL_MAP
        self._connected = True  # Keine echte Verbindung nötig
        logger.info("YFinanceConnector initialisiert (kein Order-Execution verfügbar).")

    def connect(self) -> bool:
        """Kein-Op – yfinance benötigt keine Verbindung."""
        logger.info("YFinanceConnector: connect() – kein Handlungsbedarf.")
        return True

    def disconnect(self) -> None:
        """Kein-Op."""
        logger.info("YFinanceConnector: disconnect().")

    def get_ohlcv(
        self, symbol: str, timeframe: str = "15m", bars: int = 200
    ) -> pd.DataFrame:
        """
        Lädt OHLCV-Daten über yfinance.

        Args:
            symbol: Symbol im MT5-Format oder yfinance-Format
            timeframe: Zeitrahmen-String, z.B. '15m', '5m', '1h'
            bars: Gewünschte Anzahl Bars (wird über 'period' approximiert)

        Returns:
            DataFrame mit Spalten: open, high, low, close, volume
        """
        yf_symbol = self._resolve_symbol(symbol)
        interval = TIMEFRAME_MAP.get(timeframe, "15m")
        period = PERIOD_MAP.get(timeframe, "5d")

        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)

            if df.empty:
                logger.warning(f"Keine Daten für {yf_symbol} [{timeframe}]")
                return pd.DataFrame()

            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]

            # Auf gewünschte Anzahl Bars begrenzen
            if len(df) > bars:
                df = df.iloc[-bars:]

            df.index.name = "time"
            logger.debug(f"yfinance OHLCV: {yf_symbol} [{timeframe}] | {len(df)} Bars")
            return df

        except Exception as e:
            logger.error(f"yfinance Fehler für {yf_symbol}: {e}")
            return pd.DataFrame()

    def get_current_price(self, symbol: str) -> dict:
        """
        Gibt den aktuellen Preis zurück (letzter Close aus 1m-Daten).

        Returns:
            dict mit 'bid', 'ask', 'spread', 'time'
        """
        yf_symbol = self._resolve_symbol(symbol)
        try:
            ticker = yf.Ticker(yf_symbol)
            data = ticker.history(period="1d", interval="1m")
            if data.empty:
                return {}
            last = data.iloc[-1]
            price = float(last["Close"])
            return {
                "bid": price,
                "ask": price,
                "spread": 0.0,
                "time": datetime.now(timezone.utc),
            }
        except Exception as e:
            logger.error(f"get_current_price Fehler für {yf_symbol}: {e}")
            return {}

    def get_account_balance(self) -> float:
        """Simulation – gibt einen fixen Demo-Kontostand zurück."""
        logger.warning("YFinanceConnector: get_account_balance() gibt Demo-Wert zurück.")
        return 10000.0

    def place_order(self, signal: "Signal") -> Optional[int]:  # noqa: F821
        """Nicht verfügbar im yfinance-Modus."""
        logger.warning(
            "YFinanceConnector: place_order() nicht verfügbar. "
            "Für echte Orders MT5Connector verwenden."
        )
        return None

    def close_position(self, ticket: int, lot_size: Optional[float] = None) -> bool:
        """Nicht verfügbar im yfinance-Modus (Demo: gibt True zurück)."""
        logger.warning(
            f"YFinanceConnector: close_position({ticket}, lot={lot_size}) – Demo-Modus."
        )
        return True

    def modify_position(self, ticket: int, new_sl: float, new_tp: Optional[float] = None) -> bool:
        """Simuliertes SL/TP-Update im Demo-Modus."""
        logger.info(
            f"YFinanceConnector: modify_position({ticket}) SL={new_sl}, TP={new_tp} – Demo."
        )
        return True

    def get_open_positions(self) -> list[dict]:
        """Gibt leere Liste zurück (keine echten Positionen)."""
        return []

    def get_news(self, hours_back: int = 4) -> list[dict]:
        """Fallback: gibt leere Liste zurück (kein MT5)."""
        return []

    def place_market_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[int]:
        """Nicht verfügbar im yfinance-Modus."""
        logger.warning("YFinanceConnector: place_market_order() nicht verfügbar.")
        return None

    def modify_position(self, ticket: int, new_sl: float) -> bool:
        """Nicht verfügbar im yfinance-Modus."""
        logger.warning("YFinanceConnector: modify_position() nicht verfügbar.")
        return False

    def close_partial_position(self, ticket: int, lot_size: float) -> bool:
        """Nicht verfügbar im yfinance-Modus."""
        logger.warning("YFinanceConnector: close_partial_position() nicht verfügbar.")
        return False

    def get_symbols(self) -> list[str]:
        """Nicht verfügbar im yfinance-Modus – ScannerAgent fällt auf config.all_symbols zurück."""
        return []

    def get_tick(self, symbol: str) -> dict:
        """Nicht verfügbar im yfinance-Modus."""
        return {}

    def _resolve_symbol(self, symbol: str) -> str:
        """Übersetzt MT5-Symbol zu yfinance-Ticker, falls nötig."""
        return self._symbol_map.get(symbol, symbol)
