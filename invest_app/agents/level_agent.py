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

    def __init__(self, fvg_min_size_pct: float = 0.0002, config: Any = None) -> None:
        super().__init__("level_agent")
        self._config = config
        self.fvg_min_size_pct = (
            getattr(config, "fvg_min_size_pct", fvg_min_size_pct)
            if config is not None
            else fvg_min_size_pct
        )

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

        # ATR für Order Blocks und Scoring
        atr = data.get("atr", self._estimate_atr(df))

        # Order Blocks
        order_blocks = self._find_order_blocks(df.iloc[-100:], atr)
        for ob in order_blocks:
            key_levels.append({
                "price": (ob["high"] + ob["low"]) / 2,
                "type": "order_block",
                "ob_type": ob["type"],
                "ob_high": ob["high"],
                "ob_low": ob["low"],
                "strength": 8,
            })

        # Psychologische Preislevels
        psych_levels = self._find_psychological_levels(current_price, atr)
        for pl in psych_levels:
            key_levels.append({
                "price": pl["price"],
                "type": "psychological",
                "strength": 8 if pl["strength"] == "strong" else 5,
                "psych_strength": pl["strength"],
            })

        # Duplikate entfernen (Level innerhalb level_dedup_threshold_pct zusammenführen)
        dedup_threshold = (
            getattr(self._config, "level_dedup_threshold_pct", 0.0005)
            if self._config is not None
            else 0.0005
        )
        key_levels = self._deduplicate_levels(key_levels, current_price, dedup_threshold)

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

        # OB-Nähe: Level-Score-Bonus prüfen
        ob_proximity_bonus = self._check_ob_proximity(order_blocks, current_price, atr)

        # level_score (0–100) aus reaction_score (1–10) + Bonuspunkte
        level_score = min(100, reaction_score * 10 + ob_proximity_bonus)

        # Level nach Preis sortieren
        key_levels_sorted = sorted(key_levels, key=lambda x: x["price"])

        return {
            "symbol": symbol,
            "key_levels": key_levels_sorted,
            "nearest_level": nearest,
            "distance_pct": round(distance_pct * 100, 3),
            "reaction_score": reaction_score,
            "level_score": level_score,
            "fvgs": fvgs,
            "order_blocks": order_blocks,
            "psychological_levels": psych_levels,
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

    def _find_order_blocks(self, ohlcv: pd.DataFrame, atr: float) -> list[dict]:
        """
        Findet Order Blocks: letzte Gegenrichtungskerze vor einem starken Impuls.
        Starker Impuls = Body > ATR × ob_impulse_atr_multiplier in Trendrichtung.
        """
        ob_impulse_mult = (
            getattr(self._config, "ob_impulse_atr_multiplier", 1.5)
            if self._config is not None
            else 1.5
        )
        order_blocks = []
        closes = ohlcv["close"].values
        opens = ohlcv["open"].values
        highs = ohlcv["high"].values
        lows = ohlcv["low"].values

        for i in range(1, len(ohlcv) - 1):
            body_size = abs(closes[i] - opens[i])
            if body_size < atr * ob_impulse_mult:
                continue

            # Starker Aufwärts-Impuls nach bearischer Kerze → bullischer OB
            if closes[i] > opens[i] and closes[i - 1] < opens[i - 1]:
                ob = {
                    "type": "bullish",
                    "high": float(highs[i - 1]),
                    "low": float(lows[i - 1]),
                    "index": int(i - 1),
                    "consumed": float(closes[-1]) < float(lows[i - 1]),
                }
                order_blocks.append(ob)

            # Starker Abwärts-Impuls nach bullischer Kerze → bearischer OB
            elif closes[i] < opens[i] and closes[i - 1] > opens[i - 1]:
                ob = {
                    "type": "bearish",
                    "high": float(highs[i - 1]),
                    "low": float(lows[i - 1]),
                    "index": int(i - 1),
                    "consumed": float(closes[-1]) > float(highs[i - 1]),
                }
                order_blocks.append(ob)

        # Nur nicht-konsumierte OBs, neueste zuerst
        return [ob for ob in reversed(order_blocks) if not ob["consumed"]]

    @staticmethod
    def _check_ob_proximity(order_blocks: list[dict], current_price: float, atr: float) -> int:
        """Gibt +15 zurück wenn Preis < 1 ATR von einem OB entfernt ist."""
        for ob in order_blocks:
            ob_mid = (ob["high"] + ob["low"]) / 2
            if abs(current_price - ob_mid) < atr:
                return 15
        return 0

    @staticmethod
    def _find_psychological_levels(current_price: float, atr: float) -> list[dict]:
        """Findet psychologische Preislevels (runde Zahlen) in der Nähe des Preises."""
        levels = []

        if current_price > 1000:
            increments = [100, 500, 1000]
        elif current_price > 100:
            increments = [10, 50, 100]
        elif current_price > 10:
            increments = [1, 5, 10]
        elif current_price > 1:
            increments = [0.1, 0.5, 1.0]
        else:
            increments = [0.01, 0.05, 0.1]

        seen: set[float] = set()
        for inc in increments:
            base = round(current_price / inc) * inc
            for multiplier in range(-3, 4):
                level_price = round(base + multiplier * inc, 5)
                distance = abs(current_price - level_price)
                if distance < atr * 3 and level_price not in seen:
                    seen.add(level_price)
                    levels.append({
                        "type": "psychological",
                        "price": level_price,
                        "distance": round(distance, 6),
                        "strength": "strong" if distance < atr else "moderate",
                    })

        return sorted(levels, key=lambda x: x["distance"])

    @staticmethod
    def _estimate_atr(df: pd.DataFrame, period: int = 14) -> float:
        """Schätzt ATR wenn kein externer Wert geliefert wird."""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])

    @staticmethod
    def _default_result(symbol: str) -> dict:
        return {
            "symbol": symbol,
            "key_levels": [],
            "nearest_level": None,
            "distance_pct": 0.0,
            "reaction_score": 0,
            "level_score": 0,
            "fvgs": [],
            "order_blocks": [],
            "psychological_levels": [],
            "daily_high": 0.0,
            "daily_low": 0.0,
            "current_price": 0.0,
            "level_count": 0,
        }
