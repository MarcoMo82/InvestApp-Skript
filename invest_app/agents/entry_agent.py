"""
Entry-Agent: Erkennt konkrete Einstiegs-Setups auf dem 5-Minuten-Chart.
Output: entry_type, entry_price, trigger_condition, setup_description
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agents.base_agent import BaseAgent


class EntryAgent(BaseAgent):
    """
    Regelbasierter Entry-Agent für den 5-Minuten-Zeitrahmen.
    Erkennt Breakouts, Pullbacks und Rejection-Setups.
    """

    def __init__(self, confirmation_candles: int = 1, config: Any = None) -> None:
        super().__init__("entry_agent")
        self.confirmation_candles = confirmation_candles
        self._config = config

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            symbol (str): Symbol
            ohlcv_entry (pd.DataFrame): 5m OHLCV-Daten
            direction (str): Erwartete Richtung ('long' oder 'short') aus Trend-Agent
            nearest_level (dict, optional): Nächstes S/R-Level aus Level-Agent
            atr_value (float, optional): ATR für Toleranz-Berechnungen

        Output:
            entry_type, entry_price, trigger_condition, setup_description,
            entry_found, candle_pattern
        """
        symbol = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv_entry")
        direction = data.get("direction", "neutral")
        nearest_level = data.get("nearest_level")
        atr = data.get("atr_value", 0.0)

        # P1.3: Spread-Filter
        current_spread_pips = data.get("current_spread_pips", 0.0)
        if current_spread_pips > 0 and self._config is not None:
            normal_spreads = getattr(self._config, "normal_spread_pips", {})
            multiplier = getattr(self._config, "spread_filter_multiplier", 3.0)
            if symbol in normal_spreads:
                normal = normal_spreads[symbol]
                if current_spread_pips > normal * multiplier:
                    ratio = current_spread_pips / normal
                    return self._no_entry(
                        symbol,
                        f"Spread zu hoch ({ratio:.1f}x Normal-Spread)"
                    )

        if df.empty or len(df) < 10:
            return self._no_entry(symbol, "Unzureichende Daten")

        if direction == "neutral":
            return self._no_entry(symbol, "Kein Trendfilter aktiv")

        # Letzte Kerzen
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])

        # Candlestick-Muster erkennen
        pattern = self._detect_candle_pattern(df.iloc[-3:])

        # Entry-Typen prüfen (Priorität: Breakout > Rejection > Pullback)
        if nearest_level:
            level_price = nearest_level["price"]
            tolerance = atr * 0.5 if atr > 0 else level_price * 0.001

            breakout = self._check_breakout(df, direction, level_price, tolerance)
            if breakout["found"]:
                # Handbuch: Breakout nur gültig wenn Volumen > 150% des 20P-Durchschnitts
                confidence = 1.0
                reasons: list[str] = []
                if "volume" in df.columns and len(df) >= 20:
                    vol_avg_20 = float(df["volume"].rolling(20).mean().iloc[-1])
                    current_vol = float(df["volume"].iloc[-1])
                    if vol_avg_20 > 0 and current_vol < vol_avg_20 * 1.5:
                        confidence *= 0.6
                        reasons.append("Breakout ohne Volumenbestätigung")

                description = breakout["description"]
                if reasons:
                    description += f" | Hinweis: {', '.join(reasons)}"

                return {
                    "symbol": symbol,
                    "entry_found": True,
                    "entry_type": "breakout",
                    "entry_price": breakout["entry_price"],
                    "trigger_condition": breakout["trigger"],
                    "setup_description": description,
                    "candle_pattern": pattern,
                    "confidence_modifier": round(confidence, 2),
                }

            rejection = self._check_rejection(df, direction, level_price, tolerance)
            if rejection["found"]:
                return {
                    "symbol": symbol,
                    "entry_found": True,
                    "entry_type": "rejection",
                    "entry_price": rejection["entry_price"],
                    "trigger_condition": rejection["trigger"],
                    "setup_description": rejection["description"],
                    "candle_pattern": pattern,
                }

        # Pullback-Entry (EMA-Bounce)
        pullback = self._check_pullback(df, direction, atr)
        if pullback["found"]:
            return {
                "symbol": symbol,
                "entry_found": True,
                "entry_type": "pullback",
                "entry_price": pullback["entry_price"],
                "trigger_condition": pullback["trigger"],
                "setup_description": pullback["description"],
                "candle_pattern": pattern,
            }

        return self._no_entry(symbol, "Kein valides Entry-Setup gefunden")

    def _check_breakout(
        self, df: pd.DataFrame, direction: str, level: float, tolerance: float
    ) -> dict:
        """Prüft auf Breakout über/unter ein Schlüssellevel."""
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])

        if direction == "long":
            # Schlusskurs über Level, vorherige Kerze darunter
            if last_close > level + tolerance and prev_close <= level:
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Breakout über {level:.5f}",
                    "description": f"Bullischer Breakout über {level:.5f} mit Schlusskurs-Bestätigung",
                }
        elif direction == "short":
            if last_close < level - tolerance and prev_close >= level:
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Breakout unter {level:.5f}",
                    "description": f"Bearischer Breakout unter {level:.5f} mit Schlusskurs-Bestätigung",
                }
        return {"found": False}

    def _check_rejection(
        self, df: pd.DataFrame, direction: str, level: float, tolerance: float
    ) -> dict:
        """Prüft auf Rejection (Wick-Ablehnung) an einem Level."""
        last = df.iloc[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        body = abs(close - open_)
        range_ = high - low

        if range_ == 0:
            return {"found": False}

        if direction == "long":
            # Preis testet Level von oben mit langem unterem Wick
            lower_wick = min(open_, close) - low
            wick_ratio = lower_wick / range_
            if abs(low - level) <= tolerance and wick_ratio > 0.5 and close > open_:
                return {
                    "found": True,
                    "entry_price": close,
                    "trigger": f"Bullische Rejection an {level:.5f}",
                    "description": f"Langer unterer Wick (Rejection) an Support {level:.5f}",
                }
        elif direction == "short":
            upper_wick = high - max(open_, close)
            wick_ratio = upper_wick / range_
            if abs(high - level) <= tolerance and wick_ratio > 0.5 and close < open_:
                return {
                    "found": True,
                    "entry_price": close,
                    "trigger": f"Bearische Rejection an {level:.5f}",
                    "description": f"Langer oberer Wick (Rejection) an Resistance {level:.5f}",
                }
        return {"found": False}

    def _check_pullback(
        self, df: pd.DataFrame, direction: str, atr: float
    ) -> dict:
        """Prüft auf Pullback zur EMA-21 in Trendrichtung."""
        close_series = df["close"]
        ema_21 = float(close_series.ewm(span=21, adjust=False).mean().iloc[-1])
        last_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])
        tolerance = atr * 0.3 if atr > 0 else ema_21 * 0.0005

        if direction == "long":
            # Preis zieht zur EMA zurück und bounced (Schlusskurs über EMA, vorher darunter)
            if (abs(last_close - ema_21) <= tolerance
                    and last_close > ema_21
                    and prev_close <= ema_21):
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Pullback zur EMA-21 ({ema_21:.5f})",
                    "description": f"Bullischer EMA-21 Bounce – Einstieg nach Pullback",
                }
        elif direction == "short":
            if (abs(last_close - ema_21) <= tolerance
                    and last_close < ema_21
                    and prev_close >= ema_21):
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Pullback zur EMA-21 ({ema_21:.5f})",
                    "description": f"Bearischer EMA-21 Bounce – Einstieg nach Pullback",
                }
        return {"found": False}

    def _detect_candle_pattern(self, df: pd.DataFrame) -> str:
        """Identifiziert das dominante Candlestick-Muster der letzten Kerzen."""
        if len(df) < 2:
            return "unbekannt"

        last = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        range_ = high - low

        if range_ == 0:
            return "doji"

        body = abs(close - open_)
        body_ratio = body / range_

        # Doji
        if body_ratio < 0.1:
            return "doji"

        # Hammer / Shooting Star
        lower_wick = min(open_, close) - low
        upper_wick = high - max(open_, close)

        if lower_wick > body * 2 and upper_wick < body * 0.5:
            return "hammer" if close > open_ else "hanging_man"

        if upper_wick > body * 2 and lower_wick < body * 0.5:
            return "shooting_star" if close < open_ else "inverted_hammer"

        # Engulfing
        prev_close = float(prev["close"])
        prev_open = float(prev["open"])
        if close > open_ and prev_close < prev_open:
            if close > prev_open and open_ < prev_close:
                return "bullish_engulfing"
        if close < open_ and prev_close > prev_open:
            if close < prev_open and open_ > prev_close:
                return "bearish_engulfing"

        # Standard-Kerzen
        return "bullish_candle" if close > open_ else "bearish_candle"

    @staticmethod
    def _no_entry(symbol: str, reason: str) -> dict:
        return {
            "symbol": symbol,
            "entry_found": False,
            "entry_type": "none",
            "entry_price": 0.0,
            "trigger_condition": reason,
            "setup_description": reason,
            "candle_pattern": "unbekannt",
        }
