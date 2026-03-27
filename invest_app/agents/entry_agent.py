"""
Entry-Agent: Erkennt konkrete Einstiegs-Setups auf dem 5-Minuten-Chart.
Output: entry_type, entry_price, trigger_condition, setup_description
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agents.base_agent import BaseAgent
from utils.patterns import get_pattern_confidence_bonus
from utils.smc import (
    find_fair_value_gaps,
    find_order_blocks,
    price_in_fvg,
    price_near_order_block,
)


class EntryAgent(BaseAgent):
    """
    Regelbasierter Entry-Agent für den 5-Minuten-Zeitrahmen.
    Erkennt Breakouts, Pullbacks und Rejection-Setups.
    """

    def __init__(self, confirmation_candles: int = 1, config: Any = None) -> None:
        super().__init__("entry_agent")
        self.confirmation_candles = confirmation_candles
        self._config = config

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Input data:
            symbol (str): Symbol
            ohlcv_entry (pd.DataFrame): 5m OHLCV-Daten
            direction (str): Erwartete Richtung ('long' oder 'short') aus Trend-Agent
            nearest_level (dict, optional): Nächstes S/R-Level aus Level-Agent
            atr_value (float, optional): ATR für Toleranz-Berechnungen

        Output:
            entry_type, entry_price, trigger_condition, setup_description,
            entry_found, candle_pattern
        """
        symbol = self._require_field(data, "symbol")
        df: pd.DataFrame = self._require_field(data, "ohlcv_entry")
        direction = data.get("direction", "neutral")
        nearest_level = data.get("nearest_level")
        atr = data.get("atr_value", 0.0)

        # P1.3: Spread-Filter
        current_spread_pips = data.get("current_spread_pips", 0.0)
        if current_spread_pips > 0 and self._config is not None:
            normal_spreads = getattr(self._config, "normal_spread_pips", {})
            multiplier = getattr(self._config, "spread_filter_multiplier", 3.0)
            if symbol in normal_spreads:
                normal = normal_spreads[symbol]
                if current_spread_pips > normal * multiplier:
                    ratio = current_spread_pips / normal
                    return self._no_entry(
                        symbol,
                        f"Spread zu hoch ({ratio:.1f}x Normal-Spread)"
                    )

        if df.empty or len(df) < 10:
            return self._no_entry(symbol, "Unzureichende Daten")

        if direction == "neutral":
            return self._no_entry(symbol, "Kein Trendfilter aktiv")

        # Letzte Kerzen
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])

        # Candlestick-Muster erkennen
        pattern = self._detect_candle_pattern(df.iloc[-3:])

        # === P3: SMC-Analyse (FVG + Order Block + Confluence) ===
        smc_meta = self._compute_smc_meta(df, direction, close, nearest_level, atr)

        # === Kap. 5: Chart-Muster (optionaler Confidence-Bonus) ===
        pattern_bonus = get_pattern_confidence_bonus(df, direction, self._config)
        if pattern_bonus > 0:
            smc_meta = dict(smc_meta)
            smc_meta["smc_confidence_bonus"] = smc_meta.get("smc_confidence_bonus", 0) + pattern_bonus

        # Entry-Typen prüfen (Priorität: Breakout > Rejection > Pullback)
        if nearest_level:
            level_price = nearest_level["price"]
            tolerance = atr * 0.5 if atr > 0 else level_price * 0.001

            breakout = self._check_breakout(df, direction, level_price, tolerance)
            if breakout["found"]:
                # Handbuch Kap. 7.1: Volumen < 150% des 20P-Durchschnitts → Trade ablehnen
                if "volume" in df.columns and len(df) >= 20:
                    vol_avg_20 = float(df["volume"].rolling(20).mean().iloc[-1])
                    current_vol = float(df["volume"].iloc[-1])
                    vol_mult = getattr(self._config, "volume_confirmation_multiplier", 1.5) if self._config is not None else 1.5
                    if vol_avg_20 > 0 and current_vol < vol_avg_20 * vol_mult:
                        return self._no_entry(
                            symbol, f"Breakout ohne Volumenbestätigung (< {vol_mult:.0%} Durchschnitt)"
                        )

                return {
                    "symbol": symbol,
                    "entry_found": True,
                    "entry_type": "breakout",
                    "entry_price": breakout["entry_price"],
                    "trigger_condition": breakout["trigger"],
                    "setup_description": breakout["description"],
                    "candle_pattern": pattern,
                    "confidence_modifier": 1.0,
                    **smc_meta,
                }

            rejection = self._check_rejection(df, direction, level_price, tolerance)
            if rejection["found"]:
                return {
                    "symbol": symbol,
                    "entry_found": True,
                    "entry_type": "rejection",
                    "entry_price": rejection["entry_price"],
                    "trigger_condition": rejection["trigger"],
                    "setup_description": rejection["description"],
                    "candle_pattern": pattern,
                    **smc_meta,
                }

        # Stop-Hunt-Reversal-Entry (Handbuch Kap. 8.5)
        stop_hunt = self.detect_stop_hunt_reversal(df, direction, atr)
        if stop_hunt["found"]:
            return {
                "symbol": symbol,
                "entry_found": True,
                "entry_type": "stop_hunt_reversal",
                "entry_price": stop_hunt["entry_price"],
                "trigger_condition": stop_hunt["trigger"],
                "setup_description": stop_hunt["description"],
                "candle_pattern": pattern,
                "confidence_modifier": 1.0,
                "smc_confidence_bonus": smc_meta.get("smc_confidence_bonus", 0) + 10,
                **{k: v for k, v in smc_meta.items() if k != "smc_confidence_bonus"},
            }

        # Pullback-Entry (EMA-Bounce)
        pullback = self._check_pullback(df, direction, atr)
        if pullback["found"]:
            return {
                "symbol": symbol,
                "entry_found": True,
                "entry_type": "pullback",
                "entry_price": pullback["entry_price"],
                "trigger_condition": pullback["trigger"],
                "setup_description": pullback["description"],
                "candle_pattern": pattern,
                **smc_meta,
            }

        return self._no_entry(symbol, "Kein valides Entry-Setup gefunden")

    def _check_breakout(
        self, df: pd.DataFrame, direction: str, level: float, tolerance: float
    ) -> dict:
        """Prüft auf Breakout über/unter ein Schlüssellevel."""
        last_close = float(df["close"].iloc[-1])
        prev_close = float(df["close"].iloc[-2])

        if direction == "long":
            # Schlusskurs über Level, vorherige Kerze darunter
            if last_close > level + tolerance and prev_close <= level:
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Breakout über {level:.5f}",
                    "description": f"Bullischer Breakout über {level:.5f} mit Schlusskurs-Bestätigung",
                }
        elif direction == "short":
            if last_close < level - tolerance and prev_close >= level:
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Breakout unter {level:.5f}",
                    "description": f"Bearischer Breakout unter {level:.5f} mit Schlusskurs-Bestätigung",
                }
        return {"found": False}

    def _check_rejection(
        self, df: pd.DataFrame, direction: str, level: float, tolerance: float
    ) -> dict:
        """Prüft auf Rejection (Wick-Ablehnung) an einem Level."""
        last = df.iloc[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        body = abs(close - open_)
        range_ = high - low

        if range_ == 0:
            return {"found": False}

        wick_ratio = getattr(self._config, "wick_body_ratio_min", 2.0) if self._config is not None else 2.0
        if direction == "long":
            # Preis testet Level von oben mit langem unterem Wick
            # Handbuch Kap. 7.3: Wick ≥ wick_body_ratio_min× Body
            lower_wick = min(open_, close) - low
            if (abs(low - level) <= tolerance
                    and body > 0
                    and (lower_wick / body) >= wick_ratio
                    and close > open_):
                return {
                    "found": True,
                    "entry_price": close,
                    "trigger": f"Bullische Rejection an {level:.5f}",
                    "description": f"Langer unterer Wick (Rejection) an Support {level:.5f}",
                }
        elif direction == "short":
            upper_wick = high - max(open_, close)
            if (abs(high - level) <= tolerance
                    and body > 0
                    and (upper_wick / body) >= wick_ratio
                    and close < open_):
                return {
                    "found": True,
                    "entry_price": close,
                    "trigger": f"Bearische Rejection an {level:.5f}",
                    "description": f"Langer oberer Wick (Rejection) an Resistance {level:.5f}",
                }
        return {"found": False}

    def _check_pullback(
        self, df: pd.DataFrame, direction: str, atr: float
    ) -> dict:
        """Prüft auf Pullback zur EMA-21 in Trendrichtung."""
        close_series = df["close"]
        ema_21 = float(close_series.ewm(span=21, adjust=False).mean().iloc[-1])
        last_close = float(close_series.iloc[-1])
        prev_close = float(close_series.iloc[-2])
        tolerance = atr * 0.3 if atr > 0 else ema_21 * 0.0005

        # Handbuch Kap. 7.2: Rücksetzer max. 61,8% des letzten Impulses
        lookback = min(20, len(df))
        impulse_high = float(df["high"].iloc[-lookback:].max())
        impulse_low = float(df["low"].iloc[-lookback:].min())
        impulse_size = abs(impulse_high - impulse_low)

        max_fib = getattr(self._config, "pullback_max_fib", 0.618) if self._config is not None else 0.618
        if direction == "long":
            if impulse_size > 0:
                pullback_depth = abs(last_close - impulse_high) / impulse_size
                if pullback_depth > max_fib:
                    return {"found": False}  # Pullback zu tief

            # Preis zieht zur EMA zurück und bounced (Schlusskurs über EMA, vorher darunter)
            if (abs(last_close - ema_21) <= tolerance
                    and last_close > ema_21
                    and prev_close <= ema_21):
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Pullback zur EMA-21 ({ema_21:.5f})",
                    "description": "Bullischer EMA-21 Bounce – Einstieg nach Pullback",
                }
        elif direction == "short":
            if impulse_size > 0:
                pullback_depth = abs(last_close - impulse_low) / impulse_size
                if pullback_depth > max_fib:
                    return {"found": False}  # Pullback zu tief

            if (abs(last_close - ema_21) <= tolerance
                    and last_close < ema_21
                    and prev_close >= ema_21):
                return {
                    "found": True,
                    "entry_price": last_close,
                    "trigger": f"Pullback zur EMA-21 ({ema_21:.5f})",
                    "description": "Bearischer EMA-21 Bounce – Einstieg nach Pullback",
                }
        return {"found": False}

    def detect_stop_hunt_reversal(
        self, df: pd.DataFrame, direction: str, atr: float
    ) -> dict:
        """
        Erkennt Liquidity Sweep / Stop-Hunt-Reversal (Handbuch Kap. 8.5).

        Kriterien:
        1. Kurs unterschreitet Swing-Low (Long) oder überschreitet Swing-High (Short)
           um max. 0.1–0.5 ATR
        2. Schließt zurück über/unter das Level (Rejection-Wick sichtbar)
        3. Rejection-Wick ≥ 2× Body oder starkes Umkehrvolumen (> 150% Durchschnitt)
        """
        if len(df) < 10 or atr <= 0:
            return {"found": False}

        last = df.iloc[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        body = abs(close - open_)

        # Swing-Level aus den letzten 10 abgeschlossenen Bars berechnen
        lookback = df.iloc[-11:-1]
        if len(lookback) < 5:
            return {"found": False}

        sweep_min_mult = getattr(self._config, "stop_hunt_sweep_min_atr", 0.1) if self._config is not None else 0.1
        sweep_max_mult = getattr(self._config, "stop_hunt_sweep_max_atr", 0.5) if self._config is not None else 0.5
        wick_ratio_sh = getattr(self._config, "wick_body_ratio_min", 2.0) if self._config is not None else 2.0
        vol_mult_sh = getattr(self._config, "volume_confirmation_multiplier", 1.5) if self._config is not None else 1.5
        sweep_tolerance_min = atr * sweep_min_mult
        sweep_tolerance_max = atr * sweep_max_mult

        if direction == "long":
            swing_low = float(lookback["low"].min())
            # Kriterium 1: Wick hat das Swing-Low um max. sweep_max_mult ATR unterschritten
            sweep_depth = swing_low - low
            if not (sweep_tolerance_min <= sweep_depth <= sweep_tolerance_max):
                return {"found": False}
            # Kriterium 2: Schlusskurs zurück über Swing-Low
            if close <= swing_low:
                return {"found": False}
            # Kriterium 3: Rejection-Wick ≥ wick_ratio_sh× Body oder Volumenbestätigung
            lower_wick = min(open_, close) - low
            wick_ok = body > 0 and (lower_wick / body) >= wick_ratio_sh
            vol_ok = False
            if "volume" in df.columns and len(df) >= 20:
                vol_avg = float(df["volume"].rolling(20).mean().iloc[-1])
                vol_ok = vol_avg > 0 and float(last["volume"]) > vol_avg * vol_mult_sh
            if not (wick_ok or vol_ok):
                return {"found": False}
            return {
                "found": True,
                "entry_price": close,
                "trigger": f"Stop-Hunt unter Swing-Low {swing_low:.5f}",
                "description": (
                    f"Liquidity Sweep unter {swing_low:.5f} "
                    f"(Tiefe {sweep_depth:.5f}) – Umkehr bestätigt"
                ),
            }

        elif direction == "short":
            swing_high = float(lookback["high"].max())
            sweep_depth = high - swing_high
            if not (sweep_tolerance_min <= sweep_depth <= sweep_tolerance_max):
                return {"found": False}
            if close >= swing_high:
                return {"found": False}
            upper_wick = high - max(open_, close)
            wick_ok = body > 0 and (upper_wick / body) >= wick_ratio_sh
            vol_ok = False
            if "volume" in df.columns and len(df) >= 20:
                vol_avg = float(df["volume"].rolling(20).mean().iloc[-1])
                vol_ok = vol_avg > 0 and float(last["volume"]) > vol_avg * vol_mult_sh
            if not (wick_ok or vol_ok):
                return {"found": False}
            return {
                "found": True,
                "entry_price": close,
                "trigger": f"Stop-Hunt über Swing-High {swing_high:.5f}",
                "description": (
                    f"Liquidity Sweep über {swing_high:.5f} "
                    f"(Höhe {sweep_depth:.5f}) – Umkehr bestätigt"
                ),
            }

        return {"found": False}

    def _detect_candle_pattern(self, df: pd.DataFrame) -> str:
        """Identifiziert das dominante Candlestick-Muster der letzten Kerzen."""
        if len(df) < 2:
            return "unbekannt"

        last = df.iloc[-1]
        prev = df.iloc[-2]
        close = float(last["close"])
        open_ = float(last["open"])
        high = float(last["high"])
        low = float(last["low"])
        range_ = high - low

        if range_ == 0:
            return "doji"

        body = abs(close - open_)
        body_ratio = body / range_

        # Doji
        if body_ratio < 0.1:
            return "doji"

        # Hammer / Shooting Star
        lower_wick = min(open_, close) - low
        upper_wick = high - max(open_, close)

        if lower_wick > body * 2 and upper_wick < body * 0.5:
            return "hammer" if close > open_ else "hanging_man"

        if upper_wick > body * 2 and lower_wick < body * 0.5:
            return "shooting_star" if close < open_ else "inverted_hammer"

        # Engulfing
        prev_close = float(prev["close"])
        prev_open = float(prev["open"])
        if close > open_ and prev_close < prev_open:
            if close > prev_open and open_ < prev_close:
                return "bullish_engulfing"
        if close < open_ and prev_close > prev_open:
            if close < prev_open and open_ > prev_close:
                return "bearish_engulfing"

        # Standard-Kerzen
        return "bullish_candle" if close > open_ else "bearish_candle"

    def _compute_smc_meta(
        self,
        df: pd.DataFrame,
        direction: str,
        close: float,
        nearest_level: dict | None,
        atr: float,
    ) -> dict:
        """
        Berechnet FVG-, OB- und Confluence-Daten (P3.1–P3.3).
        Gibt ein Meta-Dict zurück das in Entry-Resultate gemergt wird.
        """
        cfg = self._config

        fvg_enabled = getattr(cfg, "fvg_enabled", True) if cfg is not None else True
        ob_enabled = getattr(cfg, "ob_enabled", True) if cfg is not None else True
        fvg_bonus = getattr(cfg, "fvg_confidence_bonus", 10) if cfg is not None else 10
        ob_bonus = getattr(cfg, "ob_confidence_bonus", 15) if cfg is not None else 15
        ob_tol = getattr(cfg, "ob_tolerance_pips", 5.0) if cfg is not None else 5.0
        triple_enabled = (
            getattr(cfg, "smc_triple_confluence_enabled", True) if cfg is not None else True
        )

        # Toleranz: ATR bevorzugen, sonst ob_tolerance_pips direkt nutzen
        tolerance = atr if atr > 0 else ob_tol

        fvg_present = False
        fvg_zone: dict | None = None
        ob_present = False
        ob_zone: dict | None = None
        smc_bonus = 0

        if fvg_enabled:
            fvgs = find_fair_value_gaps(df, direction)
            fvg_present, fvg_zone = price_in_fvg(close, fvgs)
            if fvg_present:
                smc_bonus += fvg_bonus

        if ob_enabled:
            obs = find_order_blocks(df, direction)
            ob_present, ob_zone = price_near_order_block(close, obs, tolerance)
            if ob_present:
                smc_bonus += ob_bonus

        triple_bonus = getattr(cfg, "smc_triple_bonus", 20) if cfg is not None else 20
        double_bonus = getattr(cfg, "smc_double_bonus", 10) if cfg is not None else 10
        at_key_level = nearest_level is not None
        confluence_bonus = (
            self._calc_smc_confluence_bonus(fvg_present, ob_present, at_key_level, triple_bonus, double_bonus)
            if triple_enabled
            else 0
        )
        smc_bonus += confluence_bonus

        return {
            "fvg_present": fvg_present,
            "fvg_zone": fvg_zone,
            "ob_present": ob_present,
            "ob_zone": ob_zone,
            "smc_confluence": int(fvg_present) + int(ob_present) + int(at_key_level),
            "smc_confidence_bonus": smc_bonus,
        }

    @staticmethod
    def _calc_smc_confluence_bonus(
        fvg_present: bool, ob_present: bool, at_key_level: bool,
        triple_bonus: int = 20, double_bonus: int = 10,
    ) -> int:
        """
        Berechnet den SMC Triple-Confluence Bonus (P3.3).
        Drei erfüllt: +triple_bonus, zwei erfüllt: +double_bonus, einer: +0.
        """
        count = int(fvg_present) + int(ob_present) + int(at_key_level)
        if count == 3:
            return triple_bonus
        if count == 2:
            return double_bonus
        return 0

    @staticmethod
    def _no_entry(symbol: str, reason: str) -> dict:
        return {
            "symbol": symbol,
            "entry_found": False,
            "entry_type": "none",
            "entry_price": 0.0,
            "trigger_condition": reason,
            "setup_description": reason,
            "candle_pattern": "unbekannt",
            "fvg_present": False,
            "fvg_zone": None,
            "ob_present": False,
            "ob_zone": None,
            "smc_confluence": 0,
            "smc_confidence_bonus": 0,
        }
