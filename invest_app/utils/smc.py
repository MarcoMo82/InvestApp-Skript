"""
SMC (Smart Money Concepts) Utilities.
Berechnet Fair Value Gaps (FVG) und Order Blocks (OB) für die Entry-Analyse.
Eigenständiges Modul – keine Imports aus agents/.
"""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def find_fair_value_gaps(
    ohlcv: pd.DataFrame, direction: str
) -> list[dict]:
    """
    Findet Fair Value Gaps (3-Kerzen-Muster) in den letzten 50 Kerzen.

    Bullish FVG: candle[i-2].high < candle[i].low → Lücke zwischen high[i-2] und low[i]
    Bearish FVG: candle[i-2].low > candle[i].high → Lücke zwischen high[i] und low[i-2]

    Args:
        ohlcv: DataFrame mit Spalten open, high, low, close, volume
        direction: "long" für bullische FVGs, "short" für bearische FVGs

    Returns:
        Liste von FVG-Dicts mit top, bottom, midpoint, candle_index
    """
    fvgs: list[dict] = []
    df = ohlcv.iloc[-50:].reset_index(drop=True)

    if len(df) < 3:
        return fvgs

    try:
        for i in range(2, len(df)):
            high_a = float(df["high"].iloc[i - 2])
            low_a = float(df["low"].iloc[i - 2])
            high_c = float(df["high"].iloc[i])
            low_c = float(df["low"].iloc[i])

            if direction == "long":
                # Bullish FVG: kein Überlapp – high der ersten Kerze unter low der dritten
                if high_a < low_c:
                    bottom = high_a
                    top = low_c
                    fvgs.append({
                        "top": top,
                        "bottom": bottom,
                        "midpoint": (top + bottom) / 2.0,
                        "candle_index": i,
                    })
            elif direction == "short":
                # Bearish FVG: kein Überlapp – low der ersten Kerze über high der dritten
                if low_a > high_c:
                    bottom = high_c
                    top = low_a
                    fvgs.append({
                        "top": top,
                        "bottom": bottom,
                        "midpoint": (top + bottom) / 2.0,
                        "candle_index": i,
                    })
    except (KeyError, IndexError) as exc:
        logger.warning("FVG-Berechnung fehlgeschlagen: %s", exc)

    return fvgs


def price_in_fvg(
    price: float, fvgs: list[dict]
) -> tuple[bool, dict | None]:
    """
    Prüft ob der aktuelle Preis innerhalb eines Fair Value Gaps liegt.

    Args:
        price: Aktueller Preis
        fvgs: Liste von FVG-Dicts (Ausgabe von find_fair_value_gaps)

    Returns:
        (True, fvg_dict) wenn Preis im FVG liegt, sonst (False, None)
    """
    for fvg in fvgs:
        if fvg["bottom"] <= price <= fvg["top"]:
            return True, fvg
    return False, None


def find_order_blocks(
    ohlcv: pd.DataFrame,
    direction: str,
    min_body_ratio: float = 0.6,
) -> list[dict]:
    """
    Findet Order Blocks in den letzten 100 Kerzen.

    Bullish OB: letzte bearische Kerze vor starkem bullischen Impuls
                (nächste 3 Kerzen schließen höher als OB-Schlusskurs)
    Bearish OB: letzte bullische Kerze vor starkem bearischen Impuls
                (nächste 3 Kerzen schließen tiefer als OB-Schlusskurs)

    Args:
        ohlcv: DataFrame mit Spalten open, high, low, close, volume
        direction: "long" für bullische OBs, "short" für bearische OBs
        min_body_ratio: Mindest-Körper-Anteil der OB-Kerze (body / range)

    Returns:
        Liste von OB-Dicts mit top, bottom, midpoint, type
    """
    obs: list[dict] = []
    df = ohlcv.iloc[-100:].reset_index(drop=True)

    if len(df) < 4:
        return obs

    try:
        for i in range(0, len(df) - 3):
            o = float(df["open"].iloc[i])
            c = float(df["close"].iloc[i])
            h = float(df["high"].iloc[i])
            low = float(df["low"].iloc[i])

            candle_range = h - low
            if candle_range == 0:
                continue

            body = abs(c - o)
            if body / candle_range < min_body_ratio:
                continue

            next_closes = [float(df["close"].iloc[i + j]) for j in range(1, 4)]

            if direction == "long" and c < o:
                # Bearische OB-Kerze: nächste 3 Kerzen schließen alle über dem OB-Schlusskurs
                if all(nc > c for nc in next_closes):
                    obs.append({
                        "top": h,
                        "bottom": low,
                        "midpoint": (h + low) / 2.0,
                        "type": "bullish",
                    })

            elif direction == "short" and c > o:
                # Bullische OB-Kerze: nächste 3 Kerzen schließen alle unter dem OB-Schlusskurs
                if all(nc < c for nc in next_closes):
                    obs.append({
                        "top": h,
                        "bottom": low,
                        "midpoint": (h + low) / 2.0,
                        "type": "bearish",
                    })

    except (KeyError, IndexError) as exc:
        logger.warning("Order-Block-Berechnung fehlgeschlagen: %s", exc)

    return obs


def price_near_order_block(
    price: float,
    obs: list[dict],
    tolerance_pips: float = 5.0,
) -> tuple[bool, dict | None]:
    """
    Prüft ob der aktuelle Preis in der Nähe eines Order Blocks liegt.

    Args:
        price: Aktueller Preis
        obs: Liste von OB-Dicts (Ausgabe von find_order_blocks)
        tolerance_pips: Toleranz in Preis-Einheiten (z.B. ATR oder Pip-Wert)

    Returns:
        (True, ob_dict) wenn Preis nahe einem OB liegt, sonst (False, None)
    """
    for ob in obs:
        if ob["bottom"] - tolerance_pips <= price <= ob["top"] + tolerance_pips:
            return True, ob
    return False, None
