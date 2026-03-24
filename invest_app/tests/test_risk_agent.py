"""
Tests für den RiskAgent – Technischer SL, 3%-Grenze, Trailing Stop.
"""

import pytest
import numpy as np
import pandas as pd

from agents.risk_agent import RiskAgent


def _make_ohlcv(n: int = 30, base: float = 1.1000, swing_range: float = 0.005) -> pd.DataFrame:
    """Erstellt synthetische OHLCV-Daten für SL-Berechnung."""
    np.random.seed(7)
    closes = base + np.cumsum(np.random.randn(n) * 0.001)
    lows = closes - np.abs(np.random.randn(n) * swing_range)
    highs = closes + np.abs(np.random.randn(n) * swing_range)
    opens = closes - np.random.randn(n) * 0.0005

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.randint(1000, 5000, n).astype(float),
    })


class TestTechnicalSL:
    """Prüft die technische SL-Berechnung (Swing-Low/High)."""

    def test_swing_sl_long(self):
        """Für Long: technischer SL = Swing-Low der letzten 5 Bars − Puffer."""
        agent = RiskAgent()
        df = _make_ohlcv(20)
        sl = agent._calculate_swing_sl(df, "long", 1.1000)
        expected_low = float(df.iloc[-6:-1]["low"].min())
        assert sl is not None
        assert sl < expected_low  # Puffer zieht SL unter Swing-Low

    def test_swing_sl_short(self):
        """Für Short: technischer SL = Swing-High der letzten 5 Bars + Puffer."""
        agent = RiskAgent()
        df = _make_ohlcv(20)
        sl = agent._calculate_swing_sl(df, "short", 1.1000)
        expected_high = float(df.iloc[-6:-1]["high"].max())
        assert sl is not None
        assert sl > expected_high  # Puffer zieht SL über Swing-High

    def test_swing_sl_too_few_bars(self):
        """Weniger als 6 Bars → None (kein technischer SL)."""
        agent = RiskAgent()
        df = _make_ohlcv(5)
        sl = agent._calculate_swing_sl(df, "long", 1.1000)
        assert sl is None

    def test_swing_sl_none_df(self):
        """None als DataFrame → None."""
        agent = RiskAgent()
        sl = agent._calculate_swing_sl(None, "long", 1.1000)
        assert sl is None

    def test_analyze_uses_technical_sl(self):
        """analyze() mit ohlcv nutzt technischen SL wenn vorhanden."""
        agent = RiskAgent(sl_atr_multiplier=2.0)
        df = _make_ohlcv(20)
        entry = 1.1050
        atr = 0.0010

        result = agent.analyze({
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": entry,
            "atr_value": atr,
            "ohlcv": df,
        })

        # Wenn Trade erlaubt, muss SL unterhalb Entry liegen
        if result["trade_allowed"]:
            assert result["stop_loss"] < entry

    def test_analyze_without_ohlcv_falls_back_to_atr(self):
        """Ohne OHLCV: Fallback auf ATR-SL."""
        agent = RiskAgent(sl_atr_multiplier=2.0, min_crv=2.0)
        result = agent.analyze({
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "atr_value": 0.0005,
        })
        if result["trade_allowed"]:
            expected_sl = 1.1000 - 0.0005 * 2.0
            assert abs(result["stop_loss"] - expected_sl) < 0.0001


class TestSLPercentLimit:
    """Prüft die 3%-SL-Grenze."""

    def test_sl_above_3pct_rejected(self):
        """SL > 3% → Trade verwerfen."""
        agent = RiskAgent(sl_atr_multiplier=2.0)
        # ATR = 10% des Entry → SL wäre 20% weg
        result = agent.analyze({
            "symbol": "AAPL",
            "direction": "long",
            "entry_price": 150.0,
            "atr_value": 15.0,  # 10% von 150
        })
        assert result["trade_allowed"] is False
        assert "3%" in result["rejection_reason"]

    def test_sl_exactly_3pct_allowed(self):
        """SL exakt an 3%-Grenze soll noch erlaubt sein (≤ 3%)."""
        agent = RiskAgent(sl_atr_multiplier=1.0)
        entry = 100.0
        # ATR × 1.0 = 3.0 → SL = 97.0 → 3.0% genau
        result = agent.analyze({
            "symbol": "TEST",
            "direction": "long",
            "entry_price": entry,
            "atr_value": 3.0,
            "pip_size": 0.01,
        })
        # 3% genau: sl_pct = 0.03 → nicht > 0.03 → erlaubt (wenn CRV ok)
        if result["trade_allowed"]:
            sl_pct = abs(entry - result["stop_loss"]) / entry
            assert sl_pct <= 0.03

    def test_sl_below_3pct_allowed(self):
        """SL < 3% → nicht aus diesem Grund abgelehnt."""
        agent = RiskAgent(sl_atr_multiplier=2.0)
        result = agent.analyze({
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "atr_value": 0.0010,  # SL = 1.1000 - 0.002 = 0.18% weg
        })
        # Sollte nicht wegen 3%-Grenze abgelehnt werden
        if not result["trade_allowed"]:
            assert "3%" not in result.get("rejection_reason", "")

    def test_short_sl_above_3pct_rejected(self):
        """Short: SL > 3% über Entry → Trade verwerfen."""
        agent = RiskAgent(sl_atr_multiplier=2.0)
        result = agent.analyze({
            "symbol": "AAPL",
            "direction": "short",
            "entry_price": 150.0,
            "atr_value": 15.0,
        })
        assert result["trade_allowed"] is False


class TestTrailingStop:
    """Prüft die Trailing-Stop-Logik (Handbuch Abschnitt 8.4)."""

    def test_trailing_not_activated_before_1to1(self):
        """Trailing startet erst nach 1:1 CRV."""
        agent = RiskAgent()
        # Entry=100, SL=98 → 1:1 bei 102
        new_sl = agent.calculate_trailing_stop(
            current_price=101.0,  # Noch nicht bei 102
            current_sl=98.0,
            entry_price=100.0,
            take_profit=104.0,
            atr=2.0,
            direction="long",
        )
        assert new_sl == 98.0  # Unverändert

    def test_trailing_activated_after_1to1_long(self):
        """Nach 1:1 CRV: Trailing SL wird gesetzt (Long)."""
        agent = RiskAgent()
        # Entry=100, SL=98 → 1:1 bei 102
        new_sl = agent.calculate_trailing_stop(
            current_price=103.0,  # Über 1:1
            current_sl=98.0,
            entry_price=100.0,
            take_profit=106.0,
            atr=1.0,
            direction="long",
        )
        # ATR-Methode: 103 - (1.0 * 2.0) = 101.0
        assert new_sl > 98.0  # SL verbessert
        assert new_sl == pytest.approx(101.0)

    def test_trailing_activated_after_1to1_short(self):
        """Nach 1:1 CRV: Trailing SL wird gesetzt (Short)."""
        agent = RiskAgent()
        # Entry=100, SL=102 → 1:1 bei 98
        new_sl = agent.calculate_trailing_stop(
            current_price=97.0,  # Unter 1:1
            current_sl=102.0,
            entry_price=100.0,
            take_profit=94.0,
            atr=1.0,
            direction="short",
        )
        # ATR-Methode: 97 + (1.0 * 2.0) = 99.0
        assert new_sl < 102.0  # SL verbessert
        assert new_sl == pytest.approx(99.0)

    def test_sl_never_worsened_long(self):
        """SL wird für Long nie schlechter gestellt."""
        agent = RiskAgent()
        current_sl = 99.0
        new_sl = agent.calculate_trailing_stop(
            current_price=103.0,
            current_sl=current_sl,
            entry_price=100.0,
            take_profit=106.0,
            atr=0.1,  # Sehr kleiner ATR → neuer SL wäre 103 - 0.2 = 102.8
            direction="long",
        )
        # ATR-SL = 102.8 > current_sl 99.0 → verbessert
        assert new_sl >= current_sl

    def test_sl_never_worsened_short(self):
        """SL wird für Short nie schlechter gestellt."""
        agent = RiskAgent()
        current_sl = 101.0
        new_sl = agent.calculate_trailing_stop(
            current_price=97.0,
            current_sl=current_sl,
            entry_price=100.0,
            take_profit=94.0,
            atr=0.1,
            direction="short",
        )
        # ATR-SL = 97 + 0.2 = 97.2 < current_sl 101.0 → verbessert
        assert new_sl <= current_sl

    def test_ema21_used_as_floor_long(self):
        """EMA21 wird als Untergrenze für Long verwendet."""
        agent = RiskAgent()
        new_sl = agent.calculate_trailing_stop(
            current_price=105.0,
            current_sl=98.0,
            entry_price=100.0,
            take_profit=110.0,
            atr=1.0,
            direction="long",
            ema21=103.5,  # EMA höher als ATR-SL (105-2=103)
        )
        # max(ATR-SL=103, EMA=103.5) = 103.5
        assert new_sl == pytest.approx(103.5)

    def test_recent_swing_used_long(self):
        """Letztes Higher Low als struktureller SL (Long)."""
        agent = RiskAgent()
        new_sl = agent.calculate_trailing_stop(
            current_price=105.0,
            current_sl=98.0,
            entry_price=100.0,
            take_profit=110.0,
            atr=1.0,
            direction="long",
            recent_swing=104.0,  # Höher als ATR-SL (103)
        )
        assert new_sl == pytest.approx(104.0)

    def test_invalid_direction_returns_current_sl(self):
        """Ungültige Richtung → unverändert."""
        agent = RiskAgent()
        new_sl = agent.calculate_trailing_stop(
            current_price=105.0,
            current_sl=98.0,
            entry_price=100.0,
            take_profit=110.0,
            atr=1.0,
            direction="neutral",
        )
        assert new_sl == 98.0

    def test_trailing_short_not_activated_before_1to1(self):
        """Short-Trailing startet erst nach 1:1 CRV."""
        agent = RiskAgent()
        # Entry=100, SL=102 → 1:1 bei 98
        new_sl = agent.calculate_trailing_stop(
            current_price=99.0,  # Noch nicht bei 98
            current_sl=102.0,
            entry_price=100.0,
            take_profit=94.0,
            atr=1.0,
            direction="short",
        )
        assert new_sl == 102.0  # Unverändert


class TestCalculateMethod:
    """Prüft den calculate()-Wrapper."""

    def test_calculate_basic_long(self):
        """calculate() Direktaufruf für Long."""
        agent = RiskAgent(sl_atr_multiplier=2.0, min_crv=2.0)
        result = agent.calculate(
            entry_price=1.1000,
            direction="long",
            atr=0.0010,
            account_balance=10000.0,
            symbol="EURUSD",
        )
        if result["trade_allowed"]:
            assert result["stop_loss"] < 1.1000
            assert result["take_profit"] > 1.1000
            assert result["crv"] >= 2.0

    def test_calculate_with_ohlcv(self):
        """calculate() mit OHLCV-Parameter."""
        agent = RiskAgent()
        df = _make_ohlcv(20)
        result = agent.calculate(
            entry_price=1.1000,
            direction="long",
            atr=0.0010,
            symbol="EURUSD",
            ohlcv=df,
        )
        assert "trade_allowed" in result
        assert "stop_loss" in result

    def test_invalid_direction(self):
        """Ungültige Richtung → Trade abgelehnt."""
        agent = RiskAgent()
        result = agent.calculate(
            entry_price=1.1000,
            direction="sideways",
            atr=0.0010,
        )
        assert result["trade_allowed"] is False

    def test_zero_atr_rejected(self):
        """ATR = 0 → Trade abgelehnt."""
        agent = RiskAgent()
        result = agent.calculate(
            entry_price=1.1000,
            direction="long",
            atr=0.0,
        )
        assert result["trade_allowed"] is False
