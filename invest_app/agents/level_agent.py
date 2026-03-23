"""
Level-Agent: Identifiziert Schlüsselzonen, S/R-Level und Fair Value Gaps.
Output: key_levels, nearest_level, distance_pct, reaction_score
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent


class LevelAgent(BaseAgent):
    """
    Regelbasierter Level-Agent.
    Berechnet Tageshoch/-tief, Support/Resistance und Fair Value Gaps.
    """

    def __init__(self, fvg_min_size_pct: float = 0.0002) -> None:
        super().__init__("level_agent")
        self.fvg_min_size_pct = fvg_min_size_pct  # Mindestgröße für FVGs

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            symbol (str): Symbol
            ohlcv (pd.DataFrame): OHLCV HTF-Daten (15m)
            current_price (float, optional): Aktueller Preis

        Output:
            key_levels, nearest_level, distance_pct, reaction_score, fvgs
        """
        symbol = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv")
        current_price = data.get("current_price", float(df["close"].iloc[-1]))

        if df.empty or len(df) < 20:
            return self._default_result(symbol)

        key_levels = []

        # Tageshoch und Tagestief (letzte 96 Bars ≈ 1 Tag bei 15m)
        daily_bars = min(96, len(df))
        daily_high = float(df["high"].iloc[-daily_bars:].max())
        daily_low = float(df["low"].iloc[-daily_bars:].min())

        key_levels.append({"price": daily_high, "type": "daily_high", "strength": 7})
        key_levels.append({"price": daily_low, "type": "daily_low", "strength": 7})

        # Wochenhoch/-tief (letzte 480 Bars ≈ 5 Tage bei 15m)
        weekly_bars = min(480, len(df))
        weekly_high = float(df["high"].iloc[-weekly_bars:].max())
        weekly_low = float(df["low"].iloc[-weekly_bars:].min())

        if weekly_high != daily_high:
            key_levels.append({"price": weekly_high, "type": "weekly_high", "strength": 9})
        if weekly_low != daily_low:
            key_levels.append({"price": weekly_low, "type": "weekly_low", "strength": 9})

        # Swing-Highs und Swing-Lows (letzte 100 Bars)
        swing_levels = self._find_swing_levels(df.iloc[-100:])
        key_levels.extend(swing_levels)

        # Fair Value Gaps
        fvgs = self._find_fvgs(df.iloc[-50:], current_price)
        for fvg in fvgs:
            key_levels.append({
                "price": fvg["midpoint"],
                "type": f"fvg_{fvg['direction']}",
                "strength": 6,
                "fvg_high": fvg["high"],
                "fvg_low": fvg["low"],
            })

        # Duplikate entfernen (Level innerhalb 0.05% zusammenführen)
        key_levels = self._deduplicate_levels(key_levels, current_price)

        # Nächstes Level und Distanz
        nearest = self._find_nearest_level(key_levels, current_price)
        distance_pct = (
            abs(nearest["price"] - current_price) / current_price
            if nearest else 0.0
        )

        # Reaktionswahrscheinlichkeit
        reaction_score = self._calculate_reaction_score(
            nearest, distance_pct, key_levels
        )

        # Level nach Preis sortieren
        key_levels_sorted = sorted(key_levels, key=lambda x: x["price"])

        return {
            "symbol": symbol,
            "key_levels": key_levels_sorted,
            "nearest_level": nearest,
            "distance_pct": round(distance_pct * 100, 3),
            "reaction_score": reaction_score,
            "fvgs": fvgs,
            "daily_high": daily_high,
            "daily_low": daily_low,
            "current_price": current_price,
            "level_count": len(key_levels),
        }

    def _find_swing_levels(self, df: pd.DataFrame) -> list[dict]:
        """Findet Swing-Highs und Swing-Lows."""
        levels = []
        highs = df["high"].values
        lows = df["low"].values

        for i in range(2, len(highs) - 2):
            # Swing High
            if (highs[i] > highs[i - 1] and highs[i] > highs[i - 2]
                    and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]):
                levels.append({"price": float(highs[i]), "type": "swing_high", "strength": 6})

            # Swing Low
            if (lows[i] < lows[i - 1] and lows[i] < lows[i - 2]
                    and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]):
                levels.append({"price": float(lows[i]), "type": "swing_low", "strength": 6})

        return levels

    def _find_fvgs(self, df: pd.DataFrame, current_price: float) -> list[dict]:
        """
        Findet Fair Value Gaps (Imbalances zwischen 3 aufeinanderfolgenden Candles).
        """
        fvgs = []
        min_size = current_price * self.fvg_min_size_pct

        for i in range(1, len(df) - 1):
            candle_1 = df.iloc[i - 1]
            candle_3 = df.iloc[i + 1]

            # Bullischer FVG: Low von Candle 3 > High von Candle 1
            if candle_3["low"] > candle_1["high"]:
                gap_size = candle_3["low"] - candle_1["high"]
                if gap_size >= min_size:
                    fvgs.append({
                        "direction": "bullish",
                        "low": float(candle_1["high"]),
                        "high": float(candle_3["low"]),
                        "midpoint": float((candle_1["high"] + candle_3["low"]) / 2),
                        "size": float(gap_size),
                    })

            # Bearischer FVG: High von Candle 3 < Low von Candle 1
            elif candle_3["high"] < candle_1["low"]:
                gap_size = candle_1["low"] - candle_3["high"]
                if gap_size >= min_size:
                    fvgs.append({
                        "direction": "bearish",
                        "low": float(candle_3["high"]),
                        "high": float(candle_1["low"]),
                        "midpoint": float((candle_3["high"] + candle_1["low"]) / 2),
                        "size": float(gap_size),
                    })

        return fvgs[-5:]  # Nur die letzten 5 FVGs

    def _deduplicate_levels(
        self, levels: list[dict], current_price: float, threshold_pct: float = 0.0005
    ) -> list[dict]:
        """Entfernt Duplikate – Level innerhalb threshold_pct werden zusammengeführt."""
        if not levels:
            return []

        sorted_levels = sorted(levels, key=lambda x: -x["strength"])
        unique: list[dict] = []

        for level in sorted_levels:
            is_duplicate = any(
                abs(level["price"] - existing["price"]) / current_price < threshold_pct
                for existing in unique
            )
            if not is_duplicate:
                unique.append(level)

        return unique

    def _find_nearest_level(
        self, levels: list[dict], current_price: float
    ) -> dict | None:
        """Findet das nächstgelegene Level zum aktuellen Preis."""
        if not levels:
            return None
        return min(levels, key=lambda x: abs(x["price"] - current_price))

    def _calculate_reaction_score(
        self, nearest: dict | None, distance_pct: float, all_levels: list[dict]
    ) -> int:
        """
        Bewertet die Wahrscheinlichkeit einer Level-Reaktion (1–10).
        Höher = wahrscheinlicher.
        """
        if nearest is None:
            return 3

        score = 5

        # Stärke des nächsten Levels
        strength = nearest.get("strength", 5)
        score += (strength - 5)

        # Distanz zum Level (je näher, desto relevanter)
        if distance_pct < 0.001:      # < 0.1%
            score += 2
        elif distance_pct < 0.003:    # < 0.3%
            score += 1
        elif distance_pct > 0.01:     # > 1%
            score -= 2

        # Mehrere Level in der Nähe (Cluster)
        cluster_count = sum(
            1 for lv in all_levels
            if abs(lv["price"] - nearest["price"]) / nearest["price"] < 0.002
        )
        if cluster_count >= 3:
            score += 1

        return max(1, min(10, score))

    @staticmethod
    def _default_result(symbol: str) -> dict:
        return {
            "symbol": symbol,
            "key_levels": [],
            "nearest_level": None,
            "distance_pct": 0.0,
            "reaction_score": 0,
            "fvgs": [],
            "daily_high": 0.0,
            "daily_low": 0.0,
            "current_price": 0.0,
            "level_count": 0,
        }
