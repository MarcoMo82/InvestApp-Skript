"""
MetaTrader 5 Connector für Marktdaten und Order-Execution.
Läuft nur auf Windows mit installiertem MT5-Terminal.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)

# MT5 ist nur auf Windows verfügbar
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None  # type: ignore
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5-Paket nicht verfügbar – MT5Connector nicht nutzbar.")

# Zeitrahmen-Mapping: String → MT5-Konstante
TIMEFRAME_MAP: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 16385,
    "4h": 16388,
    "1d": 16408,
} if MT5_AVAILABLE else {}


class MT5Connector:
    """
    Wrapper für MetaTrader 5 mit vollständiger Fehlerbehandlung.
    Ermöglicht Marktdaten-Abruf und Order-Ausführung.
    """

    def __init__(self, login: int, password: str, server: str, path: str = "") -> None:
        if not MT5_AVAILABLE:
            raise EnvironmentError(
                "MetaTrader5 ist nicht installiert. Unter Linux/Mac den YFinanceConnector verwenden."
            )
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self._connected = False

    def connect(self) -> bool:
        """Stellt Verbindung zum MT5-Terminal her."""
        init_kwargs: dict = {}
        if self.path:
            init_kwargs["path"] = self.path

        if not mt5.initialize(**init_kwargs):
            logger.error(f"MT5 initialize fehlgeschlagen: {mt5.last_error()}")
            return False

        authorized = mt5.login(self.login, password=self.password, server=self.server)
        if not authorized:
            logger.error(f"MT5 Login fehlgeschlagen: {mt5.last_error()}")
            mt5.shutdown()
            return False

        account_info = mt5.account_info()
        if account_info is None:
            logger.error("Konnte Account-Info nicht abrufen.")
            return False

        self._connected = True
        logger.info(
            f"MT5 verbunden | Account: {account_info.login} | "
            f"Balance: {account_info.balance} {account_info.currency} | "
            f"Server: {self.server}"
        )
        return True

    def disconnect(self) -> None:
        """Trennt die Verbindung zum MT5-Terminal."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 Verbindung getrennt.")

    def get_ohlcv(
        self, symbol: str, timeframe: str = "15m", bars: int = 200
    ) -> pd.DataFrame:
        """
        Lädt OHLCV-Daten für ein Symbol.

        Args:
            symbol: MT5-Symbol, z.B. 'EURUSD'
            timeframe: Zeitrahmen-String, z.B. '15m', '5m', '1h'
            bars: Anzahl der Kerzen

        Returns:
            DataFrame mit Spalten: open, high, low, close, volume, time
        """
        self._require_connection()
        tf = self._get_timeframe(timeframe)

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, bars)
        if rates is None or len(rates) == 0:
            logger.error(f"Keine Daten für {symbol} [{timeframe}]: {mt5.last_error()}")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume"]].set_index("time")
        logger.debug(f"OHLCV geladen: {symbol} [{timeframe}] | {len(df)} Bars")
        return df

    def get_current_price(self, symbol: str) -> dict:
        """
        Gibt Bid/Ask-Preise für ein Symbol zurück.

        Returns:
            dict mit 'bid', 'ask', 'spread', 'time'
        """
        self._require_connection()
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            logger.error(f"Kein Tick für {symbol}: {mt5.last_error()}")
            return {}
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": round(tick.ask - tick.bid, 6),
            "time": datetime.utcfromtimestamp(tick.time),
        }

    def get_account_balance(self) -> float:
        """Gibt das aktuelle Konto-Guthaben zurück."""
        self._require_connection()
        info = mt5.account_info()
        return float(info.balance) if info else 0.0

    def place_order(self, signal: "Signal") -> Optional[int]:  # noqa: F821
        """
        Platziert eine Market-Order basierend auf einem Signal.

        Args:
            signal: Signal-Objekt mit entry_price, stop_loss, take_profit, lot_size

        Returns:
            MT5-Ticket-Nummer oder None bei Fehler
        """
        self._require_connection()

        symbol_info = mt5.symbol_info(signal.instrument)
        if symbol_info is None:
            logger.error(f"Symbol {signal.instrument} nicht gefunden.")
            return None

        order_type = mt5.ORDER_TYPE_BUY if str(signal.direction) == "long" else mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(signal.instrument)
        ask = price.ask if order_type == mt5.ORDER_TYPE_BUY else price.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": signal.instrument,
            "volume": float(signal.lot_size),
            "type": order_type,
            "price": ask,
            "sl": float(signal.stop_loss),
            "tp": float(signal.take_profit),
            "deviation": 10,
            "magic": 123456,
            "comment": "InvestApp",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else ""
            logger.error(f"Order fehlgeschlagen: retcode={retcode} | {comment}")
            return None

        logger.info(
            f"Order ausgeführt: {signal.instrument} {signal.direction} | "
            f"Ticket: {result.order} | Lot: {signal.lot_size} | Price: {ask}"
        )
        return result.order

    def close_position(self, ticket: int) -> bool:
        """Schließt eine offene Position anhand des Tickets."""
        self._require_connection()

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning(f"Position {ticket} nicht gefunden.")
            return False

        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol)
        close_price = price.bid if close_type == mt5.ORDER_TYPE_SELL else price.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": 10,
            "magic": 123456,
            "comment": "InvestApp Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Schließen von {ticket} fehlgeschlagen: {result}")
            return False

        logger.info(f"Position {ticket} geschlossen.")
        return True

    def get_open_positions(self) -> list[dict]:
        """Gibt alle offenen Positionen zurück."""
        self._require_connection()
        positions = mt5.positions_get()
        if positions is None:
            return []
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "long" if p.type == 0 else "short",
                "volume": p.volume,
                "open_price": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "open_time": datetime.utcfromtimestamp(p.time),
            }
            for p in positions
        ]

    def _require_connection(self) -> None:
        if not self._connected:
            raise ConnectionError("MT5 nicht verbunden. Zuerst connect() aufrufen.")

    def _get_timeframe(self, timeframe: str) -> int:
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unbekannter Zeitrahmen: {timeframe}. Gültig: {list(TIMEFRAME_MAP.keys())}")
        return tf
