"""
Volatilitäts-Agent: Bewertet ATR, Session-Qualität und Marktphase.
Output: volatility_ok, market_phase, setup_allowed, atr_value
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from .base_agent import BaseAgent


class VolatilityAgent(BaseAgent):
    """
    Regelbasierter Volatilitäts-Agent.
    Prüft ob die aktuellen Marktbedingungen für einen Trade geeignet sind.
    """

    def __init__(
        self,
        atr_period: int = 14,
        min_atr_pct: float = 0.0003,  # Mindest-ATR als % des Preises
        max_atr_pct: float = 0.015,   # Maximale ATR (zu hohe Volatilität)
    ) -> None:
        super().__init__("volatility_agent")
        self.atr_period = atr_period
        self.min_atr_pct = min_atr_pct
        self.max_atr_pct = max_atr_pct

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            symbol (str): Symbol
            ohlcv (pd.DataFrame): OHLCV-Daten

        Output:
            volatility_ok, market_phase, setup_allowed, atr_value, atr_pct,
            session, is_compression, is_expansion
        """
        symbol = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv")

        if df.empty or len(df) < self.atr_period + 1:
            return self._default_result(symbol, "Unzureichende Daten")

        # ATR berechnen
        atr = self._calculate_atr(df)
        close = float(df["close"].iloc[-1])
        atr_pct = atr / close if close > 0 else 0.0

        # Session bestimmen
        session = self._get_current_session()

        # Marktphase erkennen
        is_compression = self._detect_compression(df)
        is_expansion = self._detect_expansion(df, atr)

        # Volatilität bewerten
        volatility_ok = (
            atr_pct >= self.min_atr_pct
            and atr_pct <= self.max_atr_pct
            and session in ("london", "new_york", "london_ny_overlap")
        )

        # Marktphase klassifizieren
        if is_compression:
            market_phase = "compression"
        elif is_expansion:
            market_phase = "expansion"
        else:
            market_phase = "normal"

        # Setup erlaubt wenn Volatilität ok und nicht in reiner Compression
        setup_allowed = volatility_ok and market_phase != "compression"

        self.logger.debug(
            f"{symbol} | ATR: {atr:.5f} ({atr_pct:.3%}) | "
            f"Phase: {market_phase} | Session: {session} | OK: {volatility_ok}"
        )

        return {
            "symbol": symbol,
            "volatility_ok": volatility_ok,
            "market_phase": market_phase,
            "setup_allowed": setup_allowed,
            "atr_value": round(atr, 6),
            "atr_pct": round(atr_pct, 6),
            "session": session,
            "is_compression": is_compression,
            "is_expansion": is_expansion,
        }

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """Berechnet den Average True Range."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        atr = tr.ewm(span=self.atr_period, adjust=False).mean().iloc[-1]
        return float(atr)

    def _detect_compression(self, df: pd.DataFrame, lookback: int = 10) -> bool:
        """
        Erkennt Preiskompression (enger werdende Candles, sinkende ATR).
        """
        if len(df) < lookback * 2:
            return False

        recent_ranges = (df["high"] - df["low"]).iloc[-lookback:]
        prior_ranges = (df["high"] - df["low"]).iloc[-lookback * 2 : -lookback]

        recent_avg = float(recent_ranges.mean())
        prior_avg = float(prior_ranges.mean())

        # Compression wenn aktuelle Ranges < 60% der vorherigen
        return recent_avg < prior_avg * 0.6 if prior_avg > 0 else False

    def _detect_expansion(self, df: pd.DataFrame, current_atr: float, lookback: int = 50) -> bool:
        """
        Erkennt Volatilitäts-Expansion (ATR deutlich über Durchschnitt).
        """
        if len(df) < lookback:
            return False

        high = df["high"].iloc[-lookback:]
        low = df["low"].iloc[-lookback:]
        close = df["close"].iloc[-lookback:]

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        avg_atr = float(tr.ewm(span=self.atr_period, adjust=False).mean().mean())
        return current_atr > avg_atr * 1.5 if avg_atr > 0 else False

    @staticmethod
    def _get_current_session() -> str:
        """Bestimmt die aktuelle Trading-Session basierend auf UTC-Zeit."""
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour

        in_london = 8 <= hour < 17
        in_ny = 13 <= hour < 22

        if in_london and in_ny:
            return "london_ny_overlap"
        elif in_london:
            return "london"
        elif in_ny:
            return "new_york"
        elif 22 <= hour or hour < 8:
            return "asia"
        else:
            return "off_hours"

    @staticmethod
    def _default_result(symbol: str, reason: str) -> dict:
        return {
            "symbol": symbol,
            "volatility_ok": False,
            "market_phase": "unknown",
            "setup_allowed": False,
            "atr_value": 0.0,
            "atr_pct": 0.0,
            "session": "unknown",
            "is_compression": False,
            "is_expansion": False,
            "error": reason,
        }
