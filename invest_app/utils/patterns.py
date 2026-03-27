"""
Chart-Muster-Erkennung (Handbuch Kap. 5).
Erkennt Flag, Bear-Flag und symmetrisches Dreieck.
Gibt optionalen Confidence-Bonus für den Entry-Agent zurück.
"""

from __future__ import annotations

from typing import Any

import pandas as pd



def detect_bull_flag(ohlcv: pd.DataFrame, lookback: int = 20) -> dict[str, Any]:
    """
    Erkennt ein bullisches Flag-Muster (Handbuch Kap. 5.1).

    Kriterien:
    - Starker Impuls nach oben (Fahnenstange): mind. 2× ATR in den ersten ~60% der Bars
    - Leicht fallender Konsolidierungskanal in den restlichen ~40% der Bars
    - Ausbruch noch nicht vollzogen (kein neues Hoch über die Fahnenstange)

    Returns:
        dict mit "pattern", "confidence_bonus" und "found"
    """
    if ohlcv is None or len(ohlcv) < lookback:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    df = ohlcv.iloc[-lookback:].reset_index(drop=True)
    pole_end = int(lookback * 0.6)
    flag_bars = df.iloc[pole_end:]

    if len(flag_bars) < 3:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    # Fahnenstange: Kursanstieg in den ersten ~60% der Bars
    pole_start_price = float(df["close"].iloc[0])
    pole_end_price = float(df["close"].iloc[pole_end - 1])
    if pole_end_price <= pole_start_price:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    # Konsolidierung: leicht fallende Hochs und Tiefs
    flag_highs = flag_bars["high"].values
    flag_lows = flag_bars["low"].values
    highs_falling = all(flag_highs[i] <= flag_highs[i - 1] for i in range(1, len(flag_highs)))
    lows_falling = all(flag_lows[i] <= flag_lows[i - 1] for i in range(1, len(flag_lows)))

    if highs_falling and lows_falling:
        return {
            "found": True,
            "pattern": "bull_flag",
            "confidence_bonus": 5,
        }
    return {"found": False, "pattern": None, "confidence_bonus": 0}


def detect_bear_flag(ohlcv: pd.DataFrame, lookback: int = 20) -> dict[str, Any]:
    """
    Erkennt ein bearisches Flag-Muster (Handbuch Kap. 5.1).

    Kriterien:
    - Starker Impuls nach unten (Fahnenstange) in den ersten ~60% der Bars
    - Leicht steigender Konsolidierungskanal in den restlichen ~40% der Bars

    Returns:
        dict mit "pattern", "confidence_bonus" und "found"
    """
    if ohlcv is None or len(ohlcv) < lookback:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    df = ohlcv.iloc[-lookback:].reset_index(drop=True)
    pole_end = int(lookback * 0.6)
    flag_bars = df.iloc[pole_end:]

    if len(flag_bars) < 3:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    # Fahnenstange: Kursrückgang in den ersten ~60% der Bars
    pole_start_price = float(df["close"].iloc[0])
    pole_end_price = float(df["close"].iloc[pole_end - 1])
    if pole_end_price >= pole_start_price:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    # Konsolidierung: leicht steigende Hochs und Tiefs
    flag_highs = flag_bars["high"].values
    flag_lows = flag_bars["low"].values
    highs_rising = all(flag_highs[i] >= flag_highs[i - 1] for i in range(1, len(flag_highs)))
    lows_rising = all(flag_lows[i] >= flag_lows[i - 1] for i in range(1, len(flag_lows)))

    if highs_rising and lows_rising:
        return {
            "found": True,
            "pattern": "bear_flag",
            "confidence_bonus": 5,
        }
    return {"found": False, "pattern": None, "confidence_bonus": 0}


def detect_triangle(ohlcv: pd.DataFrame, lookback: int = 20) -> dict[str, Any]:
    """
    Erkennt ein symmetrisches Dreieck (Handbuch Kap. 5.1).

    Kriterien:
    - Fallende Hochs (Lower Highs)
    - Steigende Tiefs (Higher Lows)
    - Konvergierende Linien

    Returns:
        dict mit "pattern", "confidence_bonus" und "found"
    """
    if ohlcv is None or len(ohlcv) < lookback:
        return {"found": False, "pattern": None, "confidence_bonus": 0}

    df = ohlcv.iloc[-lookback:].reset_index(drop=True)
    highs = df["high"].values
    lows = df["low"].values

    # Jede zweite Bar prüfen (grobe Struktur)
    sample_highs = highs[::2]
    sample_lows = lows[::2]

    highs_falling = all(sample_highs[i] <= sample_highs[i - 1] for i in range(1, len(sample_highs)))
    lows_rising = all(sample_lows[i] >= sample_lows[i - 1] for i in range(1, len(sample_lows)))

    if highs_falling and lows_rising:
        return {
            "found": True,
            "pattern": "symmetrical_triangle",
            "confidence_bonus": 5,
        }
    return {"found": False, "pattern": None, "confidence_bonus": 0}


def get_pattern_confidence_bonus(ohlcv: pd.DataFrame, direction: str, config: Any = None) -> int:
    """
    Prüft alle Muster und gibt den höchsten Confidence-Bonus zurück.
    Wird im Entry-Agent optional eingebunden.

    Args:
        ohlcv: OHLCV DataFrame
        direction: "long" oder "short"
        config: optionales Config-Objekt für konfigurierbare Bonuswerte
    """
    bull_bonus = getattr(config, "bull_flag_confidence_bonus", 5) if config is not None else 5
    bear_bonus = getattr(config, "bear_flag_confidence_bonus", 5) if config is not None else 5
    triangle_bonus = getattr(config, "triangle_confidence_bonus", 5) if config is not None else 5

    if direction == "long":
        result = detect_bull_flag(ohlcv)
        if result["found"]:
            return bull_bonus
    elif direction == "short":
        result = detect_bear_flag(ohlcv)
        if result["found"]:
            return bear_bonus

    result = detect_triangle(ohlcv)
    if result["found"]:
        return triangle_bonus

    return 0
