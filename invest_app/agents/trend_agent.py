"""
Trend-Agent: Regelbasierte Trendanalyse via EMA, Higher High/Lower Low, BoS/CHoCH.
Output: direction, strength_score, structure_status, long_allowed, short_allowed
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .base_agent import BaseAgent


class TrendAgent(BaseAgent):
    """
    Regelbasierter Trend-Agent für den 15-Minuten-Zeitrahmen.
    Berechnet EMAs, Marktstruktur und gibt Trendrichtung aus.
    """

    def __init__(self, ema_periods: list[int] | None = None) -> None:
        super().__init__("trend_agent")
        self.ema_periods = ema_periods or [9, 21, 50, 200]

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            symbol (str): Symbol
            ohlcv (pd.DataFrame): OHLCV-Daten mit mindestens 200 Bars

        Output:
            direction, strength_score, structure_status,
            long_allowed, short_allowed, ema_values
        """
        symbol = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv")

        if df.empty or len(df) < max(self.ema_periods):
            self.logger.warning(f"Unzureichende Daten für {symbol}: {len(df)} Bars")
            return self._neutral_result(symbol, "Unzureichende Datenlage")

        # EMAs berechnen
        ema_values = {}
        for period in self.ema_periods:
            ema_values[f"ema_{period}"] = float(
                df["close"].ewm(span=period, adjust=False).mean().iloc[-1]
            )

        close = float(df["close"].iloc[-1])

        # EMA-Alignment prüfen
        ema_9 = ema_values["ema_9"]
        ema_21 = ema_values["ema_21"]
        ema_50 = ema_values["ema_50"]
        ema_200 = ema_values["ema_200"]

        bullish_alignment = ema_9 > ema_21 > ema_50 > ema_200
        bearish_alignment = ema_9 < ema_21 < ema_50 < ema_200
        above_200 = close > ema_200
        below_200 = close < ema_200

        # Marktstruktur: Higher Highs / Lower Lows
        structure = self._analyze_structure(df)

        # Stärke-Score berechnen (1–10)
        strength_score = self._calculate_strength(
            bullish_alignment, bearish_alignment, above_200, below_200, structure
        )

        # Richtung bestimmen
        if bullish_alignment and structure["hh_hl"]:
            direction = "long"
            structure_status = "bullish structure intact"
        elif bearish_alignment and structure["lh_ll"]:
            direction = "short"
            structure_status = "bearish structure intact"
        elif above_200:
            direction = "long"
            structure_status = "above 200 EMA, mixed structure"
        elif below_200:
            direction = "short"
            structure_status = "below 200 EMA, mixed structure"
        else:
            direction = "neutral"
            structure_status = "no clear trend"

        # BoS / CHoCH erkennen
        bos_choch = self._detect_bos_choch(df, direction)

        return {
            "symbol": symbol,
            "direction": direction,
            "strength_score": strength_score,
            "structure_status": structure_status,
            "long_allowed": direction in ("long",),
            "short_allowed": direction in ("short",),
            "ema_values": ema_values,
            "close": close,
            "bos_detected": bos_choch["bos"],
            "choch_detected": bos_choch["choch"],
            "hh_hl": structure["hh_hl"],
            "lh_ll": structure["lh_ll"],
        }

    def _analyze_structure(self, df: pd.DataFrame, lookback: int = 20) -> dict:
        """Prüft auf Higher High/Higher Low und Lower High/Lower Low."""
        highs = df["high"].iloc[-lookback:].values
        lows = df["low"].iloc[-lookback:].values

        # Lokale Pivots
        pivot_highs = [
            highs[i]
            for i in range(1, len(highs) - 1)
            if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]
        ]
        pivot_lows = [
            lows[i]
            for i in range(1, len(lows) - 1)
            if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]
        ]

        hh_hl = False
        lh_ll = False

        if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
            hh_hl = pivot_highs[-1] > pivot_highs[-2] and pivot_lows[-1] > pivot_lows[-2]
            lh_ll = pivot_highs[-1] < pivot_highs[-2] and pivot_lows[-1] < pivot_lows[-2]

        return {"hh_hl": hh_hl, "lh_ll": lh_ll}

    def _detect_bos_choch(self, df: pd.DataFrame, current_direction: str) -> dict:
        """Einfache BoS/CHoCH-Erkennung über Swing-High/Low Brüche."""
        recent = df.iloc[-30:]
        bos = False
        choch = False

        recent_high = float(recent["high"].iloc[:-5].max())
        recent_low = float(recent["low"].iloc[:-5].min())
        current_close = float(df["close"].iloc[-1])

        if current_direction == "long":
            # BoS = Schlusskurs über dem letzten Swing-Hoch (bullische Fortsetzung)
            bos = current_close > recent_high
        elif current_direction == "short":
            # BoS = Schlusskurs unter dem letzten Swing-Tief (bearische Fortsetzung)
            bos = current_close < recent_low

        # CHoCH = Bruch entgegen dem Trend
        if current_direction == "long":
            choch = current_close < recent_low
        elif current_direction == "short":
            choch = current_close > recent_high

        return {"bos": bos, "choch": choch}

    def _calculate_strength(
        self,
        bullish_alignment: bool,
        bearish_alignment: bool,
        above_200: bool,
        below_200: bool,
        structure: dict,
    ) -> int:
        score = 5  # Neutral

        if bullish_alignment:
            score += 3
        elif bearish_alignment:
            score -= 3

        if above_200:
            score += 1
        elif below_200:
            score -= 1

        if structure["hh_hl"]:
            score += 1
        elif structure["lh_ll"]:
            score -= 1

        return max(1, min(10, score))

    @staticmethod
    def _neutral_result(symbol: str, reason: str) -> dict:
        return {
            "symbol": symbol,
            "direction": "neutral",
            "strength_score": 5,
            "structure_status": reason,
            "long_allowed": False,
            "short_allowed": False,
            "ema_values": {},
            "close": 0.0,
            "bos_detected": False,
            "choch_detected": False,
            "hh_hl": False,
            "lh_ll": False,
        }
