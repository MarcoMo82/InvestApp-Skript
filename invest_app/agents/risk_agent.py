"""
Risk-Agent: Berechnet SL, TP, CRV und Positionsgröße.
Output: stop_loss, take_profit, crv, lot_size, trade_allowed
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from agents.base_agent import BaseAgent


class RiskAgent(BaseAgent):
    """
    Regelbasierter Risk-Agent.
    Berechnet ATR-basierten Stop-Loss, Take-Profit und Lot-Größe.
    """

    def __init__(
        self,
        sl_atr_multiplier: float = 2.0,
        min_crv: float = 2.0,
        risk_per_trade: float = 0.01,
        min_lot: float = 0.01,
        max_lot: float = 10.0,
        config: Any = None,
    ) -> None:
        super().__init__("risk_agent")
        # config-Parameter haben Vorrang wenn übergeben
        if config is not None:
            self.sl_atr_multiplier = getattr(config, "atr_sl_multiplier", sl_atr_multiplier)
            self.min_crv = getattr(config, "min_crv", min_crv)
            self.risk_per_trade = getattr(config, "risk_per_trade", risk_per_trade)
        else:
            self.sl_atr_multiplier = sl_atr_multiplier
            self.min_crv = min_crv
            self.risk_per_trade = risk_per_trade
        self.min_lot = min_lot
        self.max_lot = max_lot
        self._config = config

    def calculate(
        self,
        entry_price: float,
        direction: str,
        atr: float,
        account_balance: float = 10000.0,
        symbol: str = "UNKNOWN",
        pip_value: float = 10.0,
        pip_size: Optional[float] = None,
        ohlcv: Optional[pd.DataFrame] = None,
    ) -> dict:
        """
        Direktaufruf für Risikoberechnung ohne dict-Wrapping.

        Args:
            entry_price: Einstiegspreis
            direction: 'long' oder 'short'
            atr: ATR-Wert
            account_balance: Kontostand
            symbol: Symbol (für Pip-Size-Ableitung)
            pip_value: Pip-Wert pro Lot
            pip_size: Pip-Größe (None = automatisch ableiten)

        Returns:
            dict mit stop_loss, take_profit, crv, lot_size, trade_allowed
        """
        data = {
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry_price,
            "atr_value": atr,
            "account_balance": account_balance,
            "pip_value": pip_value,
        }
        if pip_size is not None:
            data["pip_size"] = pip_size
        if ohlcv is not None:
            data["ohlcv"] = ohlcv
        return self.analyze(data)

    def analyze(self, data: Any = None, **kwargs: Any) -> dict:
        """
        Input data:
            symbol (str): Symbol
            direction (str): 'long' oder 'short'
            entry_price (float): Einstiegspreis
            atr_value (float): Aktueller ATR-Wert
            account_balance (float): Kontostand in Basiswährung
            pip_value (float, optional): Pip-Wert für Lot-Berechnung (default: 10.0 für Forex)
            pip_size (float, optional): Pip-Größe (default: 0.0001 für 4-stellige Forex-Paare)

        Output:
            stop_loss, take_profit, crv, lot_size, sl_pips, trade_allowed, rejection_reason
        """
        if data is None:
            data = {}

        symbol = self._require_field(data, "symbol")
        direction = self._require_field(data, "direction")
        entry_price = self._require_field(data, "entry_price")
        atr = self._require_field(data, "atr_value")
        balance = data.get("account_balance", 10000.0)
        pip_value = data.get("pip_value", 10.0)
        pip_size = data.get("pip_size", self._infer_pip_size(symbol, entry_price))
        ohlcv: Optional[pd.DataFrame] = data.get("ohlcv")

        if entry_price <= 0 or atr <= 0:
            return self._rejected(symbol, "Ungültiger Entry-Preis oder ATR")

        # ATR-basierter SL (Fallback)
        atr_sl_distance = atr * self.sl_atr_multiplier

        # Technischer SL (Swing-Low/High) hat Vorrang
        tech_sl = self._calculate_swing_sl(ohlcv, direction, entry_price)

        if direction == "long":
            atr_stop = entry_price - atr_sl_distance
            # Technischer SL: wähle den der mehr Schutz bietet (= weiter weg vom Entry)
            if tech_sl is not None:
                stop_loss = min(atr_stop, tech_sl)  # kleinerer Wert = weiter unten = mehr Puffer
            else:
                stop_loss = atr_stop
            sl_distance = entry_price - stop_loss
            take_profit = entry_price + (sl_distance * self.min_crv)
        elif direction == "short":
            atr_stop = entry_price + atr_sl_distance
            if tech_sl is not None:
                stop_loss = max(atr_stop, tech_sl)  # größerer Wert = weiter oben = mehr Puffer
            else:
                stop_loss = atr_stop
            sl_distance = stop_loss - entry_price
            take_profit = entry_price - (sl_distance * self.min_crv)
        else:
            return self._rejected(symbol, f"Ungültige Richtung: {direction}")

        # Instrument-abhängige SL-Grenze prüfen
        max_sl = self._get_max_sl_distance(entry_price, atr)
        if sl_distance > max_sl:
            instrument_type = "Forex (80 Pips)" if entry_price < 100 else "Aktie/Index (3%)"
            return self._rejected(
                symbol,
                f"SL-Distanz {sl_distance:.5f} überschreitet Maximum {max_sl:.5f} ({instrument_type})"
            )

        # 3%-Grenze: SL > 3% des Entry-Preises → Trade verwerfen
        sl_pct = sl_distance / entry_price if entry_price > 0 else 0.0
        if sl_pct > 0.03:
            return self._rejected(symbol, f"SL > 3% des Preises ({sl_pct:.2%})")

        # CRV berechnen
        sl_diff = abs(entry_price - stop_loss)
        tp_diff = abs(entry_price - take_profit)
        crv = tp_diff / sl_diff if sl_diff > 0 else 0.0

        if crv < self.min_crv:
            return self._rejected(
                symbol, f"CRV {crv:.2f} unter Minimum {self.min_crv}"
            )

        # Stop-Loss in Pips
        sl_pips = sl_diff / pip_size if pip_size > 0 else 0.0

        # Positionsgröße berechnen (1% Regel)
        risk_amount = balance * self.risk_per_trade
        lot_size = self._calculate_lot_size(risk_amount, sl_pips, pip_value)

        # Plausibilitätsprüfung
        if stop_loss <= 0 or take_profit <= 0:
            return self._rejected(symbol, "Ungültige SL/TP-Werte")

        self.logger.debug(
            f"{symbol} {direction} | Entry: {entry_price:.5f} | "
            f"SL: {stop_loss:.5f} | TP: {take_profit:.5f} | "
            f"CRV: 1:{crv:.2f} | Lot: {lot_size} | SL-Pips: {sl_pips:.1f}"
        )

        return {
            "symbol": symbol,
            "direction": direction,
            "stop_loss": round(stop_loss, 6),
            "take_profit": round(take_profit, 6),
            "crv": round(crv, 2),
            "lot_size": lot_size,
            "sl_pips": round(sl_pips, 1),
            "sl_distance": round(sl_distance, 6),
            "risk_amount": round(risk_amount, 2),
            "trade_allowed": True,
            "rejection_reason": None,
        }

    def _calculate_lot_size(
        self, risk_amount: float, sl_pips: float, pip_value: float
    ) -> float:
        """
        Berechnet die Lot-Größe basierend auf Risikomenge und SL-Pips.
        Formel: Lot = Risikomenge / (SL_Pips * Pip_Wert_pro_Lot)
        """
        if sl_pips <= 0 or pip_value <= 0:
            return self.min_lot

        lot = risk_amount / (sl_pips * pip_value)
        lot = max(self.min_lot, min(self.max_lot, lot))

        # Auf 2 Dezimalstellen runden (Standard-Lot-Schrittweite)
        return round(lot, 2)

    @staticmethod
    def _get_max_sl_distance(entry_price: float, atr: float) -> float:
        """
        Instrument-Typ aus Preisgröße ableiten:
        - Forex (Preis < 100): max 80 Pips = 80 × 0.0001 = 0.008
        - Aktien/Indices (Preis >= 100): max 3% des Entry-Preises
        """
        if entry_price < 100:  # Forex
            pip_size = 0.0001
            max_pips = 80
            return max_pips * pip_size
        else:  # Aktien, Indices
            return entry_price * 0.03

    @staticmethod
    def _infer_pip_size(symbol: str, price: float) -> float:
        """Leitet die Pip-Größe aus Symbol und Preis ab."""
        symbol_upper = symbol.upper()

        # JPY-Paare haben 2 Nachkommastellen → Pip = 0.01
        if "JPY" in symbol_upper:
            return 0.01

        # Krypto: sehr kleiner Pip-Wert
        if symbol_upper in ("BTCUSD", "BTC-USD"):
            return 1.0
        if symbol_upper in ("ETHUSD", "ETH-USD"):
            return 0.1

        # Aktien: Pip = 0.01
        known_stocks = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"}
        if symbol_upper in known_stocks:
            return 0.01

        # Standard Forex: 4 Nachkommastellen → Pip = 0.0001
        return 0.0001

    def calculate_trailing_stop(
        self,
        current_price: float,
        current_sl: float,
        entry_price: float,
        take_profit: float,
        atr: float,
        direction: str,
        ema21: float,
        swing_ref: float,
    ) -> float:
        """
        Berechnet einen verbesserten Trailing Stop.

        Logik (Long):
          Kandidat = min(swing_ref, ema21 - atr, current_price - 1.5*atr)
          Neuer SL nur wenn Kandidat > current_sl (SL verbessert sich)

        Logik (Short):
          Kandidat = max(swing_ref, ema21 + atr, current_price + 1.5*atr)
          Neuer SL nur wenn Kandidat < current_sl

        Returns:
            Neuer SL-Wert (oder unveränderter current_sl wenn keine Verbesserung)
        """
        if direction == "long":
            candidate = min(swing_ref, ema21 - atr, current_price - 1.5 * atr)
            # Nur verbessern (SL nach oben ziehen), niemals unter Entry
            candidate = max(candidate, entry_price) if candidate > current_sl else current_sl
            return round(candidate, 6) if candidate > current_sl else current_sl
        elif direction == "short":
            candidate = max(swing_ref, ema21 + atr, current_price + 1.5 * atr)
            candidate = min(candidate, entry_price) if candidate < current_sl else current_sl
            return round(candidate, 6) if candidate < current_sl else current_sl
        return current_sl

    @staticmethod
    def _calculate_swing_sl(
        ohlcv: Optional[pd.DataFrame], direction: str, entry_price: float
    ) -> Optional[float]:
        """
        Berechnet technischen SL aus den letzten 5 Bars (Swing-Low/High).
        Long: Swing-Low der letzten 5 Bars − 2-Pip-Puffer
        Short: Swing-High der letzten 5 Bars + 2-Pip-Puffer
        """
        if ohlcv is None or len(ohlcv) < 6:
            return None

        recent = ohlcv.iloc[-6:-1]  # letzte 5 abgeschlossene Bars
        tick_puffer = entry_price * 0.0002  # ~2 Pips Puffer

        if direction == "long":
            return float(recent["low"].min()) - tick_puffer
        elif direction == "short":
            return float(recent["high"].max()) + tick_puffer
        return None

    def calculate_trailing_stop(
        self,
        current_price: float,
        current_sl: float,
        entry_price: float,
        take_profit: float,
        atr: float,
        direction: str,
        ema21: Optional[float] = None,
        recent_swing: Optional[float] = None,
    ) -> float:
        """
        Berechnet neuen Trailing Stop (Handbuch Abschnitt 8.4).

        Aktiviert erst wenn 1:1 CRV erreicht.
        ATR-Methode: primär (ATR × 2.0 vom aktuellen Hoch/Tief)
        EMA-Methode: sekundär
        Structural: letztes Higher Low / Lower High

        SL wird nie verschlechtert – nur verbessert.
        """
        sl_distance = abs(entry_price - current_sl)

        if direction == "long":
            one_to_one = entry_price + sl_distance
            if current_price < one_to_one:
                return current_sl  # 1:1 noch nicht erreicht

            new_sl = current_price - (atr * 2.0)
            if ema21 is not None:
                new_sl = max(new_sl, ema21)
            if recent_swing is not None:
                new_sl = max(new_sl, recent_swing)
            # Nur verbessern: SL darf nicht tiefer als aktuell
            return max(current_sl, new_sl)

        elif direction == "short":
            one_to_one = entry_price - sl_distance
            if current_price > one_to_one:
                return current_sl  # 1:1 noch nicht erreicht

            new_sl = current_price + (atr * 2.0)
            if ema21 is not None:
                new_sl = min(new_sl, ema21)
            if recent_swing is not None:
                new_sl = min(new_sl, recent_swing)
            # Nur verbessern: SL darf nicht höher als aktuell
            return min(current_sl, new_sl)

        return current_sl

    @staticmethod
    def _rejected(symbol: str, reason: str) -> dict:
        return {
            "symbol": symbol,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "crv": 0.0,
            "lot_size": 0.0,
            "sl_pips": 0.0,
            "sl_distance": 0.0,
            "risk_amount": 0.0,
            "trade_allowed": False,
            "rejection_reason": reason,
        }
