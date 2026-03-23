"""
Trend-Agent: Regelbasierte Trendanalyse via EMA, Higher High/Lower Low, BoS/CHoCH.
Output: direction, strength_score, structure_status, long_allowed, short_allowed
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent


class TrendAgent(BaseAgent):
    """
    Regelbasierter Trend-Agent für den 15-Minuten-Zeitrahmen.
    Berechnet EMAs, Marktstruktur und gibt Trendrichtung aus.
    """

    def __init__(
        self,
        ema_periods: Optional[list] = None,
        config: Any = None,
        data_connector: Any = None,
    ) -> None:
        super().__init__("trend_agent")
        self.ema_periods = ema_periods or (config.ema_periods if config else [9, 21, 50, 200])
        self._config = config
        self._data_connector = data_connector

    def analyze(self, data: Any = None, symbol: Optional[str] = None, **kwargs: Any) -> dict:
        """
        Analyse kann entweder über dict oder direkt mit symbol aufgerufen werden.

        Direktaufruf: agent.analyze(symbol="AAPL")
        Dict-Aufruf:  agent.analyze({"symbol": "AAPL", "ohlcv": df})

        Input data dict:
            symbol (str): Symbol
            ohlcv (pd.DataFrame): OHLCV-Daten mit mindestens 200 Bars

        Output:
            direction, strength_score, structure_status,
            long_allowed, short_allowed, ema_values
        """
        # Direktaufruf mit symbol= Keyword-Argument
        if symbol is not None and (data is None or not isinstance(data, dict)):
            if self._data_connector is None:
                return self._neutral_result(symbol, "Kein data_connector konfiguriert")
            timeframe = self._config.htf_timeframe if self._config else "15m"
            bars = self._config.htf_bars if self._config else 200
            ohlcv = self._data_connector.get_ohlcv(symbol, timeframe, bars)
            data = {"symbol": symbol, "ohlcv": ohlcv}
        elif data is None:
            data = {}

        sym = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv")

        if df.empty or len(df) < max(self.ema_periods):
            self.logger.warning(f"Unzureichende Daten für {sym}: {len(df)} Bars")
            return self._neutral_result(sym, "Unzureichende Datenlage")

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

        # ATR berechnen für Seitwärtsmarkt-Erkennung (NaN-sicher)
        high = df["high"]
        low = df["low"]
        tr_series = pd.concat([
            high - low,
            (high - df["close"].shift(1)).abs(),
            (low - df["close"].shift(1)).abs(),
        ], axis=1).max(axis=1)

        atr_current = float(tr_series.iloc[-1])
        if len(df) < 20:
            atr_avg = float(tr_series.mean())
        else:
            atr_avg_raw = tr_series.rolling(20).mean().iloc[-1]
            if pd.isna(atr_avg_raw) or atr_avg_raw == 0:
                atr_avg = float(tr_series.mean())
            else:
                atr_avg = float(atr_avg_raw)

        # Seitwärtsmarkt prüfen – überschreibt direction wenn erkannt
        if self._detect_sideways(df, atr_current, atr_avg):
            direction = "sideways"
            structure_status = "sideways market"
            strength_score = 3

        return {
            "symbol": sym,
            "direction": direction,
            "strength_score": strength_score,
            "structure_status": structure_status,
            "long_allowed": direction == "long",
            "short_allowed": direction == "short",
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
    def _detect_sideways(ohlcv: pd.DataFrame, atr: float, atr_avg: float) -> bool:
        """
        Seitwärtsmarkt wenn:
        1. ATR < 70% des 20P-Durchschnitts (geringe Volatilität)
        2. Letzten 10 Kerzen: kein klares HH/HL oder LH/LL Pattern
        """
        # Bedingung 1: ATR-Verhältnis
        if atr_avg > 0 and (atr / atr_avg) < 0.7:
            return True

        # Bedingung 2: Keine klare Struktur in letzten 10 Kerzen
        recent = ohlcv.tail(10)
        highs = recent["high"].values
        lows = recent["low"].values

        hh_count = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
        ll_count = sum(1 for i in range(1, len(lows)) if lows[i] < lows[i - 1])
        hl_count = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i - 1])
        lh_count = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])

        # Kein dominantes Muster: weder Uptrend noch Downtrend klar erkennbar
        trend_score = abs((hh_count + hl_count) - (ll_count + lh_count))
        if trend_score <= 2:
            return True  # Zu ausgeglichen = Seitwärts

        return False

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
