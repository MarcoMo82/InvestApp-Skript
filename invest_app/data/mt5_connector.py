"""
MetaTrader 5 Connector für Marktdaten und Order-Execution.
Läuft nur auf Windows mit installiertem MT5-Terminal.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
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
        if result is not None and result.retcode == 10027:  # AutoTrading disabled
            logger.warning("[Order] AutoTrading deaktiviert → Fallback auf Datei-Protokoll")
            signal_dict = {
                "symbol": signal.instrument,
                "direction": "buy" if str(signal.direction) == "long" else "sell",
                "volume": float(signal.lot_size),
                "sl": float(signal.stop_loss),
                "tp": float(signal.take_profit),
            }
            self.write_order_file(signal_dict)
            return self.read_order_result()

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

    def write_order_file(self, signal: dict) -> bool:
        """Schreibt Order in pending_order.json für MQL5 EA."""
        from config import config as app_config
        order = {
            "timestamp": time.time(),
            "symbol": signal.get("symbol"),
            "direction": signal.get("direction"),
            "volume": signal.get("volume", 0.01),
            "sl": signal.get("sl"),
            "tp": signal.get("tp"),
            "comment": "InvestApp",
            "status": "pending",
        }
        common_path = getattr(app_config, "mt5_common_files_path", "")
        if common_path:
            path = Path(common_path) / "pending_order.json"
        else:
            path = Path(app_config.output_dir) / "pending_order.json"
        with open(path, "w") as f:
            json.dump(order, f, indent=2)
        logger.info(
            f"[Order] Datei geschrieben: {signal.get('symbol')} {signal.get('direction')} "
            f"@ SL={signal.get('sl')}"
        )
        return True

    def read_order_result(self, timeout_seconds: int = 10) -> dict:
        """Wartet auf Ergebnis vom EA (pending_order.json status != pending)."""
        from config import config as app_config
        common_path = getattr(app_config, "mt5_common_files_path", "")
        if common_path:
            path = Path(common_path) / "pending_order.json"
        else:
            path = Path(app_config.output_dir) / "pending_order.json"
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get("status") != "pending":
                    return data
            except Exception:
                pass
            time.sleep(0.2)
        return {"status": "timeout", "error": "EA hat nicht geantwortet"}

    def close_position(self, ticket: int, lot_size: Optional[float] = None) -> bool:
        """
        Schließt eine offene Position anhand des Tickets.
        lot_size: Wenn angegeben, wird nur dieser Anteil geschlossen (Partial Close).
        """
        self._require_connection()

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning(f"Position {ticket} nicht gefunden.")
            return False

        pos = position[0]
        volume = lot_size if lot_size is not None else pos.volume
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol)
        close_price = price.bid if close_type == mt5.ORDER_TYPE_SELL else price.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(volume),
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

        logger.info(f"Position {ticket} geschlossen (Lot: {volume}).")
        return True

    def modify_position(self, ticket: int, new_sl: float, new_tp: Optional[float] = None) -> bool:
        """Ändert SL (und optional TP) einer offenen Position via TRADE_ACTION_SLTP."""
        self._require_connection()

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning(f"modify_position: Position {ticket} nicht gefunden.")
            return False

        pos = position[0]
        tp = new_tp if new_tp is not None else pos.tp

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": ticket,
            "sl": float(new_sl),
            "tp": float(tp),
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"modify_position {ticket} fehlgeschlagen: {result}")
            return False

        logger.info(f"Position {ticket}: SL → {new_sl}, TP → {tp}")
        return True

    def get_news(self, hours_back: int = 4) -> list[dict]:
        """Ruft Nachrichten aus MetaTrader 5 ab."""
        if not MT5_AVAILABLE or not self._connected:
            return []
        try:
            from datetime import timedelta
            date_to = datetime.now(timezone.utc)
            date_from = date_to - timedelta(hours=hours_back)
            news = mt5.news_get(date_from, date_to)
            if news is None:
                return []
            result = []
            for item in news:
                result.append({
                    "timestamp": item.time,
                    "keyword": item.subject if hasattr(item, "subject") else "",
                    "topic": item.category if hasattr(item, "category") else "",
                    "body": item.body if hasattr(item, "body") else "",
                    "source": "metatrader5",
                })
            return result
        except Exception as e:
            self.logger.error(f"MT5 News Fehler: {e}")
            return []

    def place_market_order(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[int]:
        """Platziert eine Market-Order mit Rohparametern (ohne Signal-Objekt)."""
        self._require_connection()

        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logger.error(f"Symbol {symbol} nicht gefunden.")
            return None

        order_type = mt5.ORDER_TYPE_BUY if direction == "long" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid

        request: dict = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot_size),
            "type": order_type,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "InvestApp-Watch",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if stop_loss is not None:
            request["sl"] = float(stop_loss)
        if take_profit is not None:
            request["tp"] = float(take_profit)

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else ""
            logger.error(f"Market-Order fehlgeschlagen: retcode={retcode} | {comment}")
            return None

        logger.info(f"Market-Order ausgeführt: {symbol} {direction} | Ticket: {result.order}")
        return result.order

    def modify_position(self, ticket: int, new_sl: float) -> bool:
        """Ändert den Stop-Loss einer offenen Position."""
        self._require_connection()

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning(f"Position {ticket} für SL-Änderung nicht gefunden.")
            return False

        pos = position[0]
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "sl": float(new_sl),
            "tp": float(pos.tp),
            "position": ticket,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"SL-Änderung für {ticket} fehlgeschlagen: {result}")
            return False

        logger.debug(f"SL für Ticket {ticket} → {new_sl:.5f}")
        return True

    def close_partial_position(self, ticket: int, lot_size: float) -> bool:
        """Schließt einen Teil einer offenen Position."""
        self._require_connection()

        position = mt5.positions_get(ticket=ticket)
        if not position:
            logger.warning(f"Position {ticket} nicht gefunden.")
            return False

        pos = position[0]
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(lot_size),
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": 10,
            "magic": 123456,
            "comment": "InvestApp Partial Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Partial Close für {ticket} fehlgeschlagen: {result}")
            return False

        logger.info(f"Partial Close {ticket}: {lot_size} Lots geschlossen.")
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

    def get_symbols_from_file(self, output_dir: str = "Output") -> list[str]:
        """
        Liest Symbole aus der von MQL5 EA exportierten available_symbols.json.
        Fallback auf mt5.symbols_get() wenn Datei nicht vorhanden.
        """
        import json
        import time
        from pathlib import Path

        cfg = getattr(self, "config", None)
        common_path = getattr(cfg, "mt5_common_files_path", "") if cfg else ""
        out_dir = str(getattr(cfg, "output_dir", output_dir)) if cfg else output_dir

        search_paths = []
        if common_path:
            search_paths.append(Path(common_path) / "available_symbols.json")
        search_paths.append(Path(out_dir) / "available_symbols.json")

        for path in search_paths:
            if not path.exists():
                continue

            age_minutes = (time.time() - path.stat().st_mtime) / 60
            if age_minutes > 5:
                logger.warning(
                    f"[Symbols] available_symbols.json ist {age_minutes:.0f} Min alt "
                    f"— EA läuft möglicherweise nicht"
                )

            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)

                symbols = [s["name"] for s in data.get("symbols", []) if s.get("name")]
                logger.info(
                    f"[Symbols] {len(symbols)} Symbole aus EA-Export geladen "
                    f"(Datei: {path.name}, Alter: {age_minutes:.1f} Min)"
                )
                return symbols
            except Exception as e:
                logger.warning(f"[Symbols] Fehler beim Lesen von {path}: {e}")

        logger.info("[Symbols] EA-Export nicht gefunden → Fallback auf mt5.symbols_get()")
        return self.get_symbols()

    def get_symbols(self) -> list[str]:
        """Gibt alle sichtbaren Symbole des Brokers zurück."""
        try:
            symbols = mt5.symbols_get()
            if symbols:
                return [s.name for s in symbols if s.visible]
            return []
        except Exception:
            return []

    def get_tick(self, symbol: str) -> dict:
        """Gibt aktuellen Bid/Ask-Tick für ein Symbol zurück."""
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                return {"bid": tick.bid, "ask": tick.ask}
            return {}
        except Exception:
            return {}

    def get_open_positions_count(self) -> int:
        """Gibt die Anzahl aktuell offener Positionen zurück."""
        if not self._connected:
            return 0
        try:
            count = mt5.positions_total()
            return count if count is not None else 0
        except Exception as e:
            logger.warning(f"get_open_positions_count Fehler: {e}")
            return 0

    def get_current_spread_pips(self, symbol: str) -> float:
        """Berechnet den aktuellen Spread in Pips aus Tick-Daten."""
        if not self._connected:
            return 0.0
        try:
            tick = mt5.symbol_info_tick(symbol)
            info = mt5.symbol_info(symbol)
            if tick is None or info is None:
                return 0.0
            spread_raw = tick.ask - tick.bid
            # Pip-Size: 10^(-(digits-1)), z.B. digits=5 → pip=0.0001
            pip_size = 10 ** (-(info.digits - 1)) if info.digits >= 1 else 1.0
            return round(spread_raw / pip_size, 2) if pip_size > 0 else 0.0
        except Exception as e:
            logger.warning(f"get_current_spread_pips für {symbol} fehlgeschlagen: {e}")
            return 0.0

    def get_today_realized_pnl(self) -> float:
        """Gibt den realisierten Tages-P&L aus MT5-History zurück."""
        if not self._connected:
            return 0.0
        try:
            from datetime import timedelta
            date_from = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            date_to = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(date_from, date_to)
            if deals is None:
                return 0.0
            return sum(d.profit for d in deals)
        except Exception as e:
            logger.warning(f"MT5-History P&L Fehler: {e}")
            return 0.0

    def _require_connection(self) -> None:
        if not self._connected:
            raise ConnectionError("MT5 nicht verbunden. Zuerst connect() aufrufen.")

    def _get_timeframe(self, timeframe: str) -> int:
        tf = TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            raise ValueError(f"Unbekannter Zeitrahmen: {timeframe}. Gültig: {list(TIMEFRAME_MAP.keys())}")
        return tf
