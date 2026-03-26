"""
ScannerAgent: Scannt Broker-Symbole und wählt Top-N nach Handelspotenzial.
Läuft vor dem Haupt-Zyklus (konfigurierbar alle 60 Minuten).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from data.symbol_provider import SymbolProvider, SymbolProviderError


class ScannerAgent:
    """Scannt MT5-Symbole und wählt Top-N nach Handelspotenzial."""

    def __init__(
        self,
        config: Any,
        connector: Any,
        symbol_provider: Optional[SymbolProvider] = None,
        order_db: Any = None,
    ) -> None:
        self.config = config
        self.connector = connector
        self.symbol_provider = symbol_provider
        self.order_db = order_db
        self.active_symbols: list[str] = []
        self.logger = logging.getLogger(__name__)

    def scan(self) -> list[str]:
        """Scannt alle verfügbaren Symbole und gibt die Top-N zurück."""
        all_symbols = self._get_broker_symbols()
        self.logger.info(f"[Scanner] {len(all_symbols)} Symbole von MT5 geladen")
        candidates = self._filter_by_category(all_symbols)
        min_score = getattr(self.config, "scanner_min_score", 10)
        scored: list[tuple[str, float, dict]] = []
        for symbol in candidates:
            score, breakdown = self._score_symbol(symbol)
            if score >= min_score:
                scored.append((symbol, score, breakdown))
        self.active_symbols, cat_excluded = self._select_top_symbols(scored)
        self.logger.info(
            f"[Scanner] {len(candidates)} gescannt, {len(scored)} gescort, "
            f"{len(self.active_symbols)} ausgewählt, {cat_excluded} durch Kategorie-Limit aussortiert"
        )

        # Symbol-Persistenz: scored Liste in DB speichern
        _order_db = self.order_db or (
            self.symbol_provider.order_db if self.symbol_provider else None
        )
        if _order_db is not None and scored:
            try:
                sym_data = [
                    {"symbol": s, "category": self._get_category(s), "score": score}
                    for s, score, _ in scored
                ]
                _order_db.save_symbols(sym_data)
                self.logger.info(f"[Scanner] {len(sym_data)} Symbole in DB persistiert")
            except Exception as e:
                self.logger.warning(f"[Scanner] DB-Speicherung fehlgeschlagen: {e}")

        return self.active_symbols

    def _get_broker_symbols(self) -> list[str]:
        """Ruft verfügbare Symbole vom SymbolProvider ab.

        Raises:
            SymbolProviderError: Wird nach oben propagiert wenn keine Quelle verfügbar.
        """
        if self.symbol_provider is None:
            raise SymbolProviderError(
                "[Scanner] Kein SymbolProvider konfiguriert – System stoppt"
            )
        return self.symbol_provider.get_symbols()

    def _get_category(self, symbol: str) -> str:
        """Klassifiziert ein Symbol in eine Kategorie."""
        s = symbol.upper()
        forex_ccy = ["EUR", "GBP", "USD", "JPY", "CHF", "AUD", "NZD", "CAD", "SEK", "NOK", "DKK", "SGD", "HKD", "MXN", "ZAR", "TRY", "PLN", "CZK", "HUF"]
        if len(s) == 6 and s[:3] in forex_ccy and s[3:] in forex_ccy:
            return "forex"
        # Forex mit Suffix (z.B. EURUSDm, EURUSD.)
        if len(s) > 6 and s[:3] in forex_ccy and s[3:6] in forex_ccy:
            return "forex"
        if any(s == x or s.startswith(x) for x in [
            "XAUUSD", "XAGUSD", "GOLD", "SILVER", "OIL", "USOIL", "BRENT",
            "NGAS", "NATURALGAS", "COPPER", "XPTUSD", "XPDUSD",
        ]):
            return "commodities"
        if any(c in s for c in ["BTC", "ETH", "LTC", "XRP", "BNB", "ADA", "SOL", "DOT", "DOGE", "MATIC", "AVAX"]):
            return "crypto"
        if any(idx in s for idx in [
            "GER40", "GER30", "DAX", "US30", "NAS100", "NAS", "SPX", "SP500",
            "UK100", "FTSE", "JP225", "AUS200", "DOW", "NDX", "CAC40", "CAC",
            "STOXX", "EU50", "IT40", "ES35", "HK50", "CN50", "SG30",
            "F40", "W20", "US500", "US2000",
        ]):
            return "indices"
        return "other"

    def _filter_by_category(self, symbols: list[str]) -> list[str]:
        """Filtert Symbole nach konfigurierten Kategorien."""
        categories = getattr(self.config, "scanner_categories", ["forex", "indices", "commodities"])
        return [s for s in symbols if self._get_category(s) in categories]

    def _score_symbol(self, symbol: str) -> tuple[float, dict]:
        """Bewertet ein Symbol nach ATR, EMA-Abstand, RSI und rundem Level.

        Returns:
            (score, breakdown) – score als float, breakdown als Detail-Dict
        """
        breakdown: dict = {}
        score = 0.0
        try:
            import pandas as pd

            timeframe = getattr(self.config, "htf_timeframe", "15m")
            ohlcv = self.connector.get_ohlcv(symbol, timeframe, 50)
            if ohlcv is None or len(ohlcv) < 20:
                return 0.0, breakdown

            # DataFrame oder Liste → pandas Series
            if hasattr(ohlcv, "columns"):
                closes = ohlcv["close"].reset_index(drop=True)
                highs = ohlcv["high"].reset_index(drop=True)
                lows = ohlcv["low"].reset_index(drop=True)
            else:
                closes = pd.Series([c["close"] if isinstance(c, dict) else c for c in ohlcv])
                highs = pd.Series([c["high"] if isinstance(c, dict) else c for c in ohlcv])
                lows = pd.Series([c["low"] if isinstance(c, dict) else c for c in ohlcv])

            # ATR-Bewertung
            tr = pd.concat(
                [highs - lows, (highs - closes.shift(1)).abs(), (lows - closes.shift(1)).abs()],
                axis=1,
            ).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            atr_avg = tr.rolling(20).mean().mean()
            if atr_avg <= 0 or pd.isna(atr):
                return 0.0, breakdown
            atr_ratio = atr / atr_avg
            if atr_ratio < 0.5 or atr_ratio > 2.5:
                return 0.0, breakdown
            if 0.7 <= atr_ratio <= 2.0:
                score += 30
                breakdown["atr"] = 30

            # EMA21-Abstand
            ema21 = closes.ewm(span=21).mean().iloc[-1]
            current = closes.iloc[-1]
            if current > 0:
                ema_dist_pct = abs(current - ema21) / current * 100
                if ema_dist_pct < 0.3:
                    score += 25
                    breakdown["ema_dist"] = 25
                elif ema_dist_pct < 0.8:
                    score += 15
                    breakdown["ema_dist"] = 15
                elif ema_dist_pct < 1.5:
                    score += 5
                    breakdown["ema_dist"] = 5

            # RSI(14)
            delta = closes.diff()
            gain = delta.where(delta > 0, 0.0).ewm(span=14).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(span=14).mean()
            rs = gain / loss.replace(0, 1e-10)
            rsi = (100 - 100 / (1 + rs)).iloc[-1]
            if 35 <= rsi <= 65:
                score += 20
                breakdown["rsi"] = 20
            elif 25 <= rsi <= 75:
                score += 10
                breakdown["rsi"] = 10
            else:
                score -= 10
                breakdown["rsi"] = -10

            # Spread-Bonus (default OK, kein Tick-Abruf erforderlich)
            score += 15
            breakdown["spread"] = 15

            # Rundes Level
            magnitude = 10 ** max(0, len(str(int(current))) - 1)
            nearest = round(current / magnitude) * magnitude
            if atr > 0:
                dist_atr = abs(current - nearest) / atr
                if dist_atr < 1.0:
                    score += 10
                    breakdown["round_level"] = 10
                elif dist_atr < 2.0:
                    score += 5
                    breakdown["round_level"] = 5

        except Exception as e:
            self.logger.warning(f"[Scanner] Score-Fehler {symbol}: {e}")
            return 0.0, {}

        result = max(0.0, score)
        breakdown["total"] = result
        return result, breakdown

    def _select_top_symbols(
        self, scored: list[tuple[str, float, dict]]
    ) -> tuple[list[str], int]:
        """Wählt Top-N Symbole unter Einhaltung kategorie-spezifischer Limits.

        Returns:
            (selected, cat_excluded) – ausgewählte Symbole und Anzahl durch Kategorie-Limit aussortierter
        """
        scored_sorted = sorted(scored, key=lambda x: x[1], reverse=True)
        max_total = getattr(self.config, "scanner_max_symbols", 10)
        respect_limits = getattr(self.config, "scanner_respect_category_limits", True)

        if not respect_limits:
            # Ohne Kategorie-Limits: einfach Top-N nach Score
            selected = [s for s, _, _ in scored_sorted[:max_total]]
            return selected, 0

        cat_limits: dict[str, int] = getattr(
            self.config,
            "scanner_category_limits",
            {"forex": 5, "indices": 3, "commodities": 2, "crypto": 0},
        )
        counts: dict[str, int] = {}
        selected: list[str] = []
        cat_excluded = 0
        for symbol, _score, _breakdown in scored_sorted:
            if len(selected) >= max_total:
                break
            cat = self._get_category(symbol)
            limit = cat_limits.get(cat, 2)
            if counts.get(cat, 0) < limit:
                selected.append(symbol)
                counts[cat] = counts.get(cat, 0) + 1
            else:
                cat_excluded += 1
        return selected, cat_excluded

    def log_watchlist(self, previous: list[str] | None = None) -> None:
        """Loggt die aktuelle Watchlist mit Änderungen gegenüber vorheriger."""
        if previous is not None:
            removed = [s for s in previous if s not in self.active_symbols]
            added = [s for s in self.active_symbols if s not in previous]
            if added or removed:
                self.logger.info(
                    f"[Scanner] Watchlist-Änderung: +{len(added)} hinzu, -{len(removed)} entfernt"
                )
                for s in added:
                    self.logger.info(f"[Scanner] +{s} neu aufgenommen")
                for s in removed:
                    self.logger.info(f"[Scanner] -{s} entfernt")
            else:
                self.logger.info("[Scanner] Watchlist unverändert")
        self.logger.info(
            f"[Scanner] Aktive Symbole ({len(self.active_symbols)}): {', '.join(self.active_symbols)}"
        )
