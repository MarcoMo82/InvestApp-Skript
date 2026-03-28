"""
Tests für den EntryAgent – Volume-Check bei Breakouts.
"""

import pytest
import numpy as np
import pandas as pd

from agents.entry_agent import EntryAgent


def _make_breakout_df(
    n: int = 50,
    level: float = 1.1050,
    breakout: bool = True,
    volume_ratio: float = 2.0,  # Volumen relativ zum 20P-Durchschnitt
) -> pd.DataFrame:
    """
    Erstellt einen DataFrame der einen Breakout über `level` simuliert.
    Die letzte Kerze bricht aus, die vorletzte liegt darunter.
    """
    np.random.seed(99)
    base = level - 0.0010
    closes = base + np.cumsum(np.random.randn(n) * 0.0003)

    # Basis-Volumen für alle Bars
    base_vol = 1000.0
    volumes = np.full(n, base_vol)

    if breakout:
        # Letzte Kerze: Breakout über Level
        closes[-1] = level + 0.0010
        closes[-2] = level - 0.0002

    # Letzte Kerze: Volumen = Ratio × Durchschnitt
    vol_avg = base_vol
    volumes[-1] = vol_avg * volume_ratio

    highs = closes + 0.0005
    lows = closes - 0.0005
    opens = closes - 0.0002

    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


class TestVolumeCheckBreakout:
    """Prüft den Volume-Check bei Breakout-Entries."""

    def test_breakout_with_high_volume_no_penalty(self):
        """Breakout mit Volumen > 150% → kein Hinweis, confidence_modifier = 1.0."""
        agent = EntryAgent()
        df = _make_breakout_df(n=50, level=1.1050, volume_ratio=2.0)
        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
            "nearest_level": {"price": 1.1050},
            "atr_value": 0.0005,
        })

        if result["entry_found"] and result["entry_type"] == "breakout":
            assert result.get("confidence_modifier", 1.0) == 1.0
            assert "Volumenbestätigung" not in result["setup_description"]

    def test_breakout_with_low_volume_rejected(self):
        """Breakout mit Volumen < 150% → Trade wird abgelehnt (entry_found=False)."""
        agent = EntryAgent()
        df = _make_breakout_df(n=50, level=1.1050, volume_ratio=1.0)  # Nur 100% = zu wenig
        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
            "nearest_level": {"price": 1.1050},
            "atr_value": 0.0005,
        })

        # Handbuch 7.1: Breakout ohne Volumen wird abgelehnt
        assert result["entry_found"] is False
        assert "Volumenbestätigung" in result["trigger_condition"]

    def test_breakout_with_very_high_volume_no_penalty(self):
        """Volumen 300% des Durchschnitts → kein Penalty (weit über 150%)."""
        agent = EntryAgent()
        df = _make_breakout_df(n=50, level=1.1050, volume_ratio=3.0)
        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
            "nearest_level": {"price": 1.1050},
            "atr_value": 0.0005,
        })

        if result["entry_found"] and result["entry_type"] == "breakout":
            # 300% des Basis-Volumens ist klar über Schwelle → kein Penalty
            assert result.get("confidence_modifier", 1.0) == 1.0

    def test_no_volume_column_no_error(self):
        """Kein Volume-Spaltename im DataFrame → kein Absturz, normales Entry."""
        agent = EntryAgent()
        df = _make_breakout_df(n=50, level=1.1050, volume_ratio=2.0)
        df = df.drop(columns=["volume"])  # Kein Volume

        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
            "nearest_level": {"price": 1.1050},
            "atr_value": 0.0005,
        })
        # Kein Absturz – confidence_modifier = 1.0 (kein Check möglich)
        if result["entry_found"] and result["entry_type"] == "breakout":
            assert result.get("confidence_modifier", 1.0) == 1.0

    def test_rejection_entry_not_affected_by_volume_check(self):
        """Rejection-Entry hat keinen Volume-Check."""
        agent = EntryAgent()

        # Rejection: Preis testet Level von oben, langer unterer Wick
        level = 1.1050
        close_p = level + 0.0002  # Bullisch
        open_p = level + 0.0010
        low_p = level - 0.0005   # Langer unterer Wick

        df = _make_breakout_df(n=50, level=level, breakout=False, volume_ratio=0.5)
        # Letzte Kerze manuell als Rejection setzen
        df.iloc[-1, df.columns.get_loc("open")] = open_p
        df.iloc[-1, df.columns.get_loc("close")] = close_p
        df.iloc[-1, df.columns.get_loc("low")] = low_p
        df.iloc[-1, df.columns.get_loc("high")] = open_p + 0.0002

        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
            "nearest_level": {"price": level},
            "atr_value": 0.0010,
        })

        # Wenn Rejection gefunden → kein confidence_modifier Penalty
        if result["entry_found"] and result["entry_type"] == "rejection":
            assert "confidence_modifier" not in result or result["confidence_modifier"] == 1.0

    def test_pullback_entry_not_affected_by_volume_check(self):
        """Pullback-Entry hat keinen Volume-Check."""
        agent = EntryAgent()
        df = _make_breakout_df(n=50, level=1.1050, breakout=False, volume_ratio=0.5)

        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
            "atr_value": 0.0010,
        })

        if result["entry_found"] and result["entry_type"] == "pullback":
            assert "confidence_modifier" not in result or result["confidence_modifier"] == 1.0

    def test_short_breakout_volume_check(self):
        """Volume-Check gilt auch für Short-Breakouts: zu wenig Volumen → abgelehnt."""
        agent = EntryAgent()
        level = 1.1050
        df = _make_breakout_df(n=50, level=level, breakout=True, volume_ratio=1.0)
        # Short-Breakout simulieren: letzte Kerze unter Level
        df.iloc[-1, df.columns.get_loc("close")] = level - 0.0010
        df.iloc[-2, df.columns.get_loc("close")] = level + 0.0002

        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "short",
            "nearest_level": {"price": level},
            "atr_value": 0.0005,
        })

        # Handbuch 7.1: Breakout ohne Volumen wird abgelehnt
        assert result["entry_found"] is False
        assert "Volumenbestätigung" in result["trigger_condition"]

    def test_no_entry_returns_correct_structure(self):
        """Kein Entry → korrekte Struktur."""
        agent = EntryAgent()
        df = _make_breakout_df(n=50, level=1.1050, breakout=False)
        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "neutral",
        })
        assert result["entry_found"] is False
        assert result["entry_type"] == "none"

    def test_insufficient_data_no_entry(self):
        """Zu wenig Daten → kein Entry."""
        agent = EntryAgent()
        df = _make_breakout_df(n=5)
        result = agent.analyze({
            "symbol": "EURUSD",
            "ohlcv_entry": df,
            "direction": "long",
        })
        assert result["entry_found"] is False


class TestFalseBreakoutFilter:
    """Tests für _is_false_breakout() – Fakeout-Erkennung."""

    def _make_fakeout_df(
        self,
        n: int = 50,
        level: float = 1.1050,
        close_above_level: bool = True,
        volume_ratio: float = 0.5,
        high_above_level: bool = True,
    ) -> pd.DataFrame:
        """
        Erstellt einen DataFrame für Fakeout-Tests.
        close_above_level=False → Kerze schließt zurück unter Level (Fakeout-Signal).
        volume_ratio: Volumen der letzten Kerze relativ zum Basis-Volumen.
        """
        np.random.seed(42)
        base = level - 0.0010
        closes = base + np.cumsum(np.random.randn(n) * 0.0003)
        closes[-2] = level - 0.0002  # Vorletzte Kerze unter Level

        base_vol = 1000.0
        volumes = np.full(n, base_vol)
        volumes[-1] = base_vol * volume_ratio

        if close_above_level:
            closes[-1] = level + 0.0005  # Schlusskurs über Level
        else:
            closes[-1] = level - 0.0003  # Schlusskurs zurück unter Level (Close-Back)

        highs = closes + 0.0005
        if high_above_level:
            highs[-1] = level + 0.0010  # Wick über Level (Breakout-Versuch)
        lows = closes - 0.0005
        opens = closes - 0.0002

        return pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })

    def test_weak_volume_and_close_back_returns_true(self):
        """Schwaches Volumen + Close zurück unter Level → _is_false_breakout gibt True zurück."""
        agent = EntryAgent()
        level = 1.1050
        # Close-Back: Kerze schließt unter Level; Volumen = 50% des Durchschnitts
        df = self._make_fakeout_df(
            level=level,
            close_above_level=False,
            volume_ratio=0.5,
        )
        result = agent._is_false_breakout(df, "long", level, atr=0.0005)
        assert result is True, "Schwaches Volumen + Close-Back muss Fakeout-Verdacht auslösen"

    def test_strong_volume_close_above_level_returns_false(self):
        """Starkes Volumen + Close über Level → _is_false_breakout gibt False zurück."""
        agent = EntryAgent()
        level = 1.1050
        # Echtes Breakout: Schlusskurs über Level, Volumen = 200% des Durchschnitts
        df = self._make_fakeout_df(
            level=level,
            close_above_level=True,
            volume_ratio=2.0,
        )
        result = agent._is_false_breakout(df, "long", level, atr=0.0005)
        assert result is False, "Starkes Volumen + Close über Level darf kein Fakeout sein"
