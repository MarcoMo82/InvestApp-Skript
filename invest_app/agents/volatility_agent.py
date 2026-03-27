"""
Volatilitäts-Agent: Bewertet ATR, Session-Qualität und Marktphase.
Output: volatility_ok, market_phase, setup_allowed, atr_value
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent


class VolatilityAgent(BaseAgent):
    """
    Regelbasierter Volatilitäts-Agent.
    Prüft ob die aktuellen Marktbedingungen für einen Trade geeignet sind.
    """

    def __init__(
        self,
        atr_period: int = 14,
        min_atr_ratio: float = 0.5,   # Mindest-Ratio: ATR / 20P-Durchschnitt
        max_atr_ratio: float = 2.0,   # Maximal-Ratio: ATR / 20P-Durchschnitt
        min_atr_pct: float = 0.0,     # Mindest-ATR in % des Preises (0 = deaktiviert)
        config: Any = None,
        data_connector: Any = None,
    ) -> None:
        super().__init__("volatility_agent")
        self.atr_period = atr_period if config is None else getattr(config, "atr_period", atr_period)
        self.min_atr_ratio = getattr(config, "min_atr_ratio", min_atr_ratio) if config is not None else min_atr_ratio
        self.max_atr_ratio = getattr(config, "max_atr_ratio", max_atr_ratio) if config is not None else max_atr_ratio
        self.min_atr_pct = min_atr_pct
        self._config = config
        self._data_connector = data_connector

    def analyze(self, data: Any = None, symbol: Optional[str] = None, **kwargs: Any) -> dict:
        """
        Analyse kann entweder über dict oder direkt mit symbol aufgerufen werden.

        Direktaufruf: agent.analyze(symbol="AAPL")
        Dict-Aufruf:  agent.analyze({"symbol": "AAPL", "ohlcv": df})

        Input data dict:
            symbol (str): Symbol
            ohlcv (pd.DataFrame): OHLCV-Daten

        Output:
            volatility_ok, market_phase, setup_allowed, atr_value, atr_pct,
            session, is_compression, is_expansion, rsi, rsi_status,
            rsi_divergence, bb_status, bb_bandwidth, approved
        """
        # Direktaufruf mit symbol= Keyword-Argument
        if symbol is not None and (data is None or not isinstance(data, dict)):
            if self._data_connector is None:
                return self._default_result(symbol, "Kein data_connector konfiguriert")
            timeframe = self._config.htf_timeframe if self._config else "15m"
            bars = self._config.htf_bars if self._config else 200
            ohlcv = self._data_connector.get_ohlcv(symbol, timeframe, bars)
            data = {"symbol": symbol, "ohlcv": ohlcv}
        elif data is None:
            data = {}

        sym = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv")

        if df.empty or len(df) < self.atr_period + 20 + 1:
            return self._default_result(sym, "Unzureichende Daten")

        # ATR-Serie und Ratio berechnen (Handbuch: ATR vs. 20P-Durchschnitt)
        atr_series = self._calculate_atr_series(df)
        atr = float(atr_series.iloc[-1])
        if pd.isna(atr) or atr == 0:
            return self._default_result(sym, "Zu wenig Daten für ATR-Berechnung")
        atr_avg_20 = float(atr_series.rolling(20).mean().iloc[-1])
        close = float(df["close"].iloc[-1])
        atr_pct = atr / close if close > 0 else 0.0

        if atr_avg_20 > 0:
            atr_ratio = atr / atr_avg_20
        else:
            atr_ratio = 1.0

        # Handbuch-Filter: Mindest-ATR in % des Preises (falls konfiguriert)
        if self.min_atr_pct > 0 and atr_pct < self.min_atr_pct:
            return {**self._default_result(sym, f"ATR zu niedrig (< {self.min_atr_pct:.2%} des Preises)"),
                    "atr_value": round(atr, 6), "atr_pct": round(atr_pct, 6),
                    "atr_ratio": round(atr_ratio, 4)}

        # Handbuch-Filter: Ratio < 0.5 → zu ruhig; > 2.0 → zu volatil
        if atr_ratio < self.min_atr_ratio:
            return {**self._default_result(sym, "ATR zu niedrig (< 50% des 20P-Durchschnitts)"),
                    "atr_value": round(atr, 6), "atr_pct": round(atr_pct, 6),
                    "atr_ratio": round(atr_ratio, 4)}
        if atr_ratio > self.max_atr_ratio:
            return {**self._default_result(sym, "ATR zu hoch (> 200% des 20P-Durchschnitts)"),
                    "atr_value": round(atr, 6), "atr_pct": round(atr_pct, 6),
                    "atr_ratio": round(atr_ratio, 4)}

        # Session bestimmen (verwendet Config-Werte falls verfügbar)
        session = self._get_current_session()

        # Marktphase erkennen
        is_compression = self._detect_compression(df)
        is_expansion = self._detect_expansion(df, atr)

        # Volatilität ok wenn Session aktiv
        volatility_ok = session in ("london", "new_york", "london_ny_overlap")

        # Marktphase klassifizieren
        if is_compression:
            market_phase = "compression"
        elif is_expansion:
            market_phase = "expansion"
        else:
            market_phase = "normal"

        # Setup erlaubt wenn Volatilität ok und nicht in reiner Compression
        setup_allowed = volatility_ok and market_phase != "compression"

        # RSI berechnen
        rsi_series = self._calculate_rsi(df)
        rsi_value = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0
        rsi_status = self._get_rsi_status(rsi_value)
        rsi_divergence = self._check_rsi_divergence(df, rsi_series)

        # Bollinger Bands berechnen
        bb_upper, bb_mid, bb_lower, bb_bandwidth_series = self._calculate_bollinger_bands(df)
        bb_bandwidth = float(bb_bandwidth_series.iloc[-1]) if not bb_bandwidth_series.empty else 0.02
        bb_status = self._get_bb_status(df, bb_upper, bb_lower, bb_bandwidth, self._config)

        # Confidence-Anpassungen durch RSI und BB
        confidence_modifier = 0.0
        if rsi_divergence:
            confidence_modifier -= 0.10
        if bb_status == "squeeze":
            confidence_modifier += 0.05
        elif bb_status in ("above_upper", "below_lower"):
            confidence_modifier -= 0.10

        self.logger.debug(
            f"{sym} | ATR: {atr:.5f} ({atr_pct:.3%}) | Ratio: {atr_ratio:.2f} | "
            f"Phase: {market_phase} | Session: {session} | OK: {volatility_ok} | "
            f"RSI: {rsi_value:.1f} ({rsi_status}) | BB: {bb_status}"
        )

        return {
            "symbol": sym,
            "volatility_ok": volatility_ok,
            "market_phase": market_phase,
            "setup_allowed": setup_allowed,
            "approved": setup_allowed,
            "atr_value": round(atr, 6),
            "atr_pct": round(atr_pct, 6),
            "atr_ratio": round(atr_ratio, 4),
            "session": session,
            "is_compression": is_compression,
            "is_expansion": is_expansion,
            "rsi": round(rsi_value, 2),
            "rsi_status": rsi_status,
            "rsi_divergence": rsi_divergence,
            "bb_status": bb_status,
            "bb_bandwidth": round(bb_bandwidth, 6),
            "confidence_modifier": round(confidence_modifier, 2),
        }

    def _calculate_rsi(self, ohlcv: pd.DataFrame, period: int = 0) -> pd.Series:
        if period == 0:
            period = getattr(self._config, "rsi_period", 14) if self._config is not None else 14
        """Berechnet den RSI(14) für die Schlusskurse."""
        delta = ohlcv["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _get_rsi_status(self, rsi: float) -> str:
        """Klassifiziert den RSI-Wert."""
        overbought = getattr(self._config, "rsi_overbought", 70) if self._config is not None else 70
        oversold = getattr(self._config, "rsi_oversold", 30) if self._config is not None else 30
        if rsi > overbought:
            return "overbought"
        elif rsi < oversold:
            return "oversold"
        elif 40 <= rsi <= 60:
            return "neutral"
        elif rsi > 60:
            return "bullish"
        else:
            return "bearish"

    @staticmethod
    def _check_rsi_divergence(ohlcv: pd.DataFrame, rsi_series: pd.Series, lookback: int = 20) -> bool:
        """
        Bearische RSI-Divergenz: Preis macht neues Hoch, RSI nicht.
        Gibt True zurück wenn bearische Divergenz erkannt.
        """
        if len(ohlcv) < lookback or len(rsi_series) < lookback:
            return False

        price_window = ohlcv["high"].iloc[-lookback:]
        rsi_window = rsi_series.iloc[-lookback:]

        # Valide Werte filtern
        valid_mask = rsi_window.notna()
        if valid_mask.sum() < 2:
            return False

        price_window = price_window[valid_mask]
        rsi_window = rsi_window[valid_mask]

        price_recent_high = float(price_window.iloc[-5:].max())
        price_prior_high = float(price_window.iloc[:-5].max())
        rsi_recent_high = float(rsi_window.iloc[-5:].max())
        rsi_prior_high = float(rsi_window.iloc[:-5].max())

        # Bearische Divergenz: Preis höher, RSI tiefer
        return price_recent_high > price_prior_high and rsi_recent_high < rsi_prior_high

    def _calculate_bollinger_bands(
        self, ohlcv: pd.DataFrame, period: int = 0, std_dev: float = 0.0
    ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        """Berechnet Bollinger Bands (aus Config: bb_period, bb_std_dev)."""
        if period == 0:
            period = getattr(self._config, "bb_period", 20) if self._config is not None else 20
        if std_dev == 0.0:
            std_dev = getattr(self._config, "bb_std_dev", 2.0) if self._config is not None else 2.0
        mid = ohlcv["close"].rolling(period).mean()
        std = ohlcv["close"].rolling(period).std()
        upper = mid + std_dev * std
        lower = mid - std_dev * std
        bandwidth = (upper - lower) / mid  # relative Bandbreite
        return upper, mid, lower, bandwidth

    @staticmethod
    def _get_bb_status(
        ohlcv: pd.DataFrame,
        bb_upper: pd.Series,
        bb_lower: pd.Series,
        bandwidth: float,
        config: Any = None,
        squeeze_threshold: float = 0.01,
        walk_lookback: int = 3,
    ) -> str:
        """Bestimmt den Bollinger-Band-Status."""
        if config is not None:
            squeeze_threshold = getattr(config, "bb_squeeze_threshold", squeeze_threshold)
        if pd.isna(bandwidth) or bandwidth == 0:
            return "neutral"

        close = ohlcv["close"]
        last_close = float(close.iloc[-1])
        last_upper = float(bb_upper.iloc[-1])
        last_lower = float(bb_lower.iloc[-1])

        if bandwidth < squeeze_threshold:
            return "squeeze"

        # Preis außerhalb der Bänder
        if last_close > last_upper:
            return "above_upper"
        if last_close < last_lower:
            return "below_lower"

        # BB-Walk: Preis schließt wiederholt am oberen/unteren Band
        recent_closes = close.iloc[-walk_lookback:]
        recent_upper = bb_upper.iloc[-walk_lookback:]
        recent_lower = bb_lower.iloc[-walk_lookback:]

        if all(c >= u * 0.998 for c, u in zip(recent_closes, recent_upper)):
            return "upper_walk"
        if all(c <= l * 1.002 for c, l in zip(recent_closes, recent_lower)):
            return "lower_walk"

        # Bandbreite wächst → Expansion
        if bandwidth > squeeze_threshold * 2:
            return "expansion"

        return "neutral"

    def _calculate_atr_series(self, df: pd.DataFrame) -> "pd.Series":
        """Berechnet den ATR als vollständige Serie (EWM)."""
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        return tr.ewm(span=self.atr_period, adjust=False).mean()

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """Berechnet den Average True Range (letzter Wert)."""
        return float(self._calculate_atr_series(df).iloc[-1])

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

        # Compression wenn aktuelle Ranges < compression_range_ratio der vorherigen
        ratio = getattr(self._config, "compression_range_ratio", 0.6) if self._config is not None else 0.6
        return recent_avg < prior_avg * ratio if prior_avg > 0 else False

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

        avg_atr_raw = tr.ewm(span=self.atr_period, adjust=False).mean().mean()
        if pd.isna(avg_atr_raw):
            return False
        avg_atr = float(avg_atr_raw)
        multiplier = getattr(self._config, "expansion_atr_multiplier", 1.5) if self._config is not None else 1.5
        return current_atr > avg_atr * multiplier if avg_atr > 0 else False

    def _get_current_session(self) -> str:
        """Bestimmt die aktuelle Trading-Session basierend auf UTC-Zeit."""
        now_utc = datetime.now(timezone.utc)
        hour = now_utc.hour

        london_open = getattr(self._config, "london_open_hour", 8) if self._config is not None else 8
        london_close = getattr(self._config, "london_close_hour", 17) if self._config is not None else 17
        ny_open = getattr(self._config, "ny_open_hour", 13) if self._config is not None else 13
        ny_close = getattr(self._config, "ny_close_hour", 22) if self._config is not None else 22

        in_london = london_open <= hour < london_close
        in_ny = ny_open <= hour < ny_close

        if in_london and in_ny:
            return "london_ny_overlap"
        elif in_london:
            return "london"
        elif in_ny:
            return "new_york"
        elif ny_close <= hour or hour < london_open:
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
            "approved": False,
            "atr_value": 0.0,
            "atr_pct": 0.0,
            "session": "unknown",
            "is_compression": False,
            "is_expansion": False,
            "rsi": 50.0,
            "rsi_status": "neutral",
            "rsi_divergence": False,
            "bb_status": "neutral",
            "bb_bandwidth": 0.0,
            "confidence_modifier": 0.0,
            "error": reason,
        }
