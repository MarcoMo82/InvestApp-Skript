"""Tests für den LevelAgent – Order Blocks und Psychologische Levels."""
import numpy as np
import pandas as pd
import pytest

from agents.level_agent import LevelAgent


def _make_ohlcv(n: int = 200, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    prices = [100.0]
    for _ in range(1, n):
        prices.append(max(prices[-1] + np.random.normal(0.05, 0.5), 1.0))
    return pd.DataFrame(
        {
            "open": [p * np.random.uniform(0.998, 1.0) for p in prices],
            "high": [p * np.random.uniform(1.001, 1.01) for p in prices],
            "low": [p * np.random.uniform(0.99, 0.999) for p in prices],
            "close": prices,
            "volume": np.random.randint(1000, 10000, n),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="15min"),
    )


class TestOrderBlocks:
    def test_order_blocks_key_in_output(self, sample_ohlcv):
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert "order_blocks" in result

    def test_order_blocks_is_list(self, sample_ohlcv):
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert isinstance(result["order_blocks"], list)

    def test_order_block_structure(self, sample_ohlcv):
        """Jeder OB hat type, high, low, index, consumed."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        for ob in result["order_blocks"]:
            assert "type" in ob
            assert ob["type"] in ("bullish", "bearish")
            assert "high" in ob
            assert "low" in ob
            assert ob["high"] >= ob["low"]
            assert "consumed" in ob
            assert ob["consumed"] is False  # nur nicht-konsumierte werden zurückgegeben

    def test_order_blocks_not_consumed(self, sample_ohlcv):
        """Zurückgegebene OBs dürfen nicht konsumiert sein."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        for ob in result["order_blocks"]:
            assert not ob["consumed"]

    def test_bullish_ob_detection(self):
        """Bearische Kerze gefolgt von starkem Aufwärts-Impuls → bullischer OB."""
        agent = LevelAgent()
        atr = 1.0
        # Kerze i-1: bearisch (close < open)
        # Kerze i: starker Aufwärts-Impuls (body > ATR*1.5, close > open)
        # Kerze i+1: neutral
        df = pd.DataFrame({
            "open":  [100.0, 99.0, 101.0, 102.0, 103.0],
            "high":  [101.0, 100.0, 104.0, 103.0, 104.0],
            "low":   [99.0,  97.0,  100.5, 101.0, 102.0],
            "close": [99.5,  97.5,  103.5, 102.5, 103.5],  # Kerze 1 bearisch, Kerze 2 starker Anstieg
            "volume": [1000] * 5,
        })
        obs = agent._find_order_blocks(df, atr)
        types = [ob["type"] for ob in obs]
        # Kerze 2 (index 2): body = 103.5 - 101.0 = 2.5 > 1.5 ATR, aufwärts → Kerze 1 bullischer OB
        assert "bullish" in types

    def test_bearish_ob_detection(self):
        """Bullische Kerze gefolgt von starkem Abwärts-Impuls → bearischer OB."""
        agent = LevelAgent()
        atr = 1.0
        df = pd.DataFrame({
            "open":  [100.0, 99.0, 103.0, 99.5, 99.0],
            "high":  [101.0, 102.0, 103.5, 100.0, 99.5],
            "low":   [99.0,  98.5,  99.5,  98.0, 98.5],
            "close": [100.5, 101.5, 100.0, 98.5, 99.0],  # Kerze 1 bullisch, Kerze 2 starker Absturz
            "volume": [1000] * 5,
        })
        obs = agent._find_order_blocks(df, atr)
        types = [ob["type"] for ob in obs]
        assert "bearish" in types

    def test_ob_in_key_levels(self, sample_ohlcv):
        """Order Blocks sollen als 'order_block' in key_levels auftauchen."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        ob_levels = [lv for lv in result["key_levels"] if lv["type"] == "order_block"]
        # Wenn OBs gefunden wurden, müssen sie in key_levels sein
        if result["order_blocks"]:
            assert len(ob_levels) > 0

    def test_level_score_present(self, sample_ohlcv):
        """level_score (0–100) muss im Output vorhanden sein."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert "level_score" in result
        assert 0 <= result["level_score"] <= 100

    def test_ob_proximity_bonus(self):
        """OB-Nähe < 1 ATR → +15 Bonus."""
        agent = LevelAgent()
        current_price = 100.0
        atr = 2.0
        # OB direkt am Preis
        obs = [{"type": "bullish", "high": 101.0, "low": 99.0}]
        bonus = agent._check_ob_proximity(obs, current_price, atr)
        assert bonus == 15

    def test_ob_no_bonus_far_away(self):
        """OB weit entfernt → kein Bonus."""
        agent = LevelAgent()
        current_price = 100.0
        atr = 0.5
        obs = [{"type": "bullish", "high": 110.0, "low": 108.0}]
        bonus = agent._check_ob_proximity(obs, current_price, atr)
        assert bonus == 0


class TestPsychologicalLevels:
    def test_psych_levels_key_in_output(self, sample_ohlcv):
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert "psychological_levels" in result

    def test_psych_levels_is_list(self, sample_ohlcv):
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        assert isinstance(result["psychological_levels"], list)

    def test_psych_level_structure(self, sample_ohlcv):
        """Jedes psychologische Level hat price, distance, strength."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        for pl in result["psychological_levels"]:
            assert "price" in pl
            assert "distance" in pl
            assert "strength" in pl
            assert pl["strength"] in ("strong", "moderate")

    def test_psych_levels_sorted_by_distance(self, sample_ohlcv):
        """Psychologische Levels sind nach Distanz sortiert."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        levels = result["psychological_levels"]
        if len(levels) > 1:
            distances = [lv["distance"] for lv in levels]
            assert distances == sorted(distances)

    def test_psych_level_high_price(self):
        """Für Preis > 1000: Inkremente 100, 500, 1000."""
        agent = LevelAgent()
        levels = agent._find_psychological_levels(5000.0, 50.0)
        prices = [lv["price"] for lv in levels]
        # Muss 5000 als rundes Level enthalten
        assert 5000.0 in prices

    def test_psych_level_forex_price(self):
        """Für Forex-Preis (0.x): Inkremente 0.01, 0.05, 0.1 — ATR groß genug für Treffer."""
        agent = LevelAgent()
        # ATR = 0.01 → 3 ATR = 0.03 → Level 1.09 (dist=0.005) und 1.10 (dist=0.015) enthalten
        levels = agent._find_psychological_levels(1.0850, 0.01)
        assert len(levels) > 0
        prices = [lv["price"] for lv in levels]
        # 1.09 oder 1.10 oder 1.08 sollte enthalten sein
        round_levels = [p for p in prices if round(p * 100) == p * 100 or abs(p - round(p, 1)) < 0.001]
        assert len(round_levels) > 0

    def test_psych_levels_in_key_levels(self, sample_ohlcv):
        """Psychologische Levels sollen in key_levels auftauchen."""
        agent = LevelAgent()
        result = agent.analyze({"symbol": "AAPL", "ohlcv": sample_ohlcv})
        psych_in_key = [lv for lv in result["key_levels"] if lv["type"] == "psychological"]
        if result["psychological_levels"]:
            assert len(psych_in_key) > 0

    def test_psych_level_distance_within_3_atr(self):
        """Nur Levels innerhalb 3 × ATR werden zurückgegeben."""
        agent = LevelAgent()
        atr = 1.0
        current_price = 100.0
        levels = agent._find_psychological_levels(current_price, atr)
        for lv in levels:
            assert lv["distance"] < atr * 3
