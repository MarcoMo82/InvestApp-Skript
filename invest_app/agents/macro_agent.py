"""
Makro-Agent: Analysiert Makro-Umfeld und News mit Claude LLM.
Output: macro_bias, event_risk, trading_allowed, reasoning
Enthält check_news_block() (P1.4) und get_risk_sentiment() (P2.3).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from agents.base_agent import BaseAgent
from utils.claude_client import ClaudeClient
from data.news_fetcher import NewsFetcher
from data.economic_calendar import EconomicCalendar

# Safe-Haven Symbole: werden bei Risk-Off bevorzugt
SAFE_HAVEN_SYMBOLS: list[str] = ["USDJPY", "USDCHF", "XAUUSD", "CHFJPY"]


def _parse_event_time(time_str: str) -> datetime:
    """Parst einen ISO-Zeit-String (mit oder ohne Z) in ein timezone-aware datetime."""
    try:
        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _extract_currencies(symbol: str) -> list[str]:
    """
    Leitet die relevanten Währungen aus einem Trading-Symbol ab.

    Beispiele:
        "EURUSD"  → ["EUR", "USD"]
        "XAUUSD"  → ["XAU", "USD"]
        "BTCUSD"  → ["BTC", "USD"]
        "AAPL"    → []  (Aktien → keine Währungsfilterung)
    """
    clean = symbol.upper().replace("=X", "").replace("-", "").replace("/", "")
    if len(clean) == 6 and clean.isalpha():
        return [clean[:3], clean[3:]]
    return []


SYSTEM_PROMPT = """Du bist ein erfahrener Makro-Analyst für Finanzmärkte.
Analysiere die bereitgestellten Nachrichten und gib eine strukturierte Bewertung zurück.
Antworte NUR mit validem JSON – kein Text davor oder danach."""

USER_PROMPT_TEMPLATE = """Analysiere folgende Marktnachrichten für {symbol}:

{news_text}

Erstelle eine Makro-Bewertung als JSON mit diesen exakten Feldern:
{{
  "macro_bias": "bullish" | "bearish" | "neutral",
  "event_risk": "low" | "medium" | "high",
  "trading_allowed": true | false,
  "key_themes": ["Thema1", "Thema2"],
  "reasoning": "Kurze Begründung in 2-3 Sätzen"
}}

Regeln:
- trading_allowed = false wenn event_risk = "high"
- Berücksichtige aktuelle geopolitische und wirtschaftliche Entwicklungen
- Sei konservativ bei Unsicherheit"""


class MacroAgent(BaseAgent):
    """LLM-gestützter Makro-Analyse-Agent."""

    def __init__(
        self,
        claude_client: ClaudeClient,
        news_fetcher: NewsFetcher,
        data_connector: Any = None,
    ) -> None:
        super().__init__("macro_agent")
        self.claude = claude_client
        self.news_fetcher = news_fetcher
        self.data_connector = data_connector

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Analysiert Makro-Umfeld für ein Symbol.

        Input data:
            symbol (str): Trading-Symbol

        Output:
            macro_bias, event_risk, trading_allowed, key_themes, reasoning,
            calendar_source, calendar_event_count
        """
        symbol = self._require_field(data, "symbol")
        currencies = _extract_currencies(symbol)

        # ── Wirtschaftskalender: event_risk bestimmen ─────────────────────
        calendar_source = "UNKNOWN"
        calendar_event_count = 0
        calendar_event_risk: str | None = None  # None = Kalender nicht verfügbar

        try:
            from config import config as _cfg
            cal = EconomicCalendar(_cfg)
            cal_events = cal.get_events(currencies) if currencies else []
            calendar_source = cal.last_source
            calendar_event_count = len(cal_events)

            # Nur zukünftige Events zählen für event_risk
            now = datetime.now(timezone.utc)
            upcoming = [
                e for e in cal_events
                if _parse_event_time(e.get("time", "")) > now
            ]
            calendar_event_risk = "high" if upcoming else "low"
        except Exception as e:
            self.logger.warning(f"[MacroAgent] Kalender-Abruf fehlgeschlagen: {e}")
            calendar_source = "UNKNOWN"

        # ── News holen (Yahoo Finance + MT5 falls verfügbar) ─────────────
        news_items = self.news_fetcher.get_yahoo_news(symbol)
        market_news = self.news_fetcher.get_finanznachrichten()
        mt5_news = (
            self.data_connector.get_news(hours_back=4)
            if self.data_connector is not None and hasattr(self.data_connector, "get_news")
            else []
        )

        all_news = (news_items + market_news + mt5_news)[:10]

        if not all_news:
            result = self._default_result(symbol, "Keine News verfügbar.")
        else:
            # News-Text für Prompt aufbereiten
            news_text = "\n".join(
                f"- [{n.get('publisher', 'unbekannt')}] {n['title']}" for n in all_news
            )
            prompt = USER_PROMPT_TEMPLATE.format(symbol=symbol, news_text=news_text)

            try:
                response = self.claude.analyze(prompt, system_prompt=SYSTEM_PROMPT)
                result = self._parse_response(response)
            except Exception as e:
                self.logger.error(f"Claude-Aufruf fehlgeschlagen: {e}")
                result = self._default_result(symbol, str(e))

            result["symbol"] = symbol
            result["news_count"] = len(all_news)

        # ── Kalender überschreibt event_risk (falls verfügbar) ────────────
        if calendar_event_risk is not None:
            result["event_risk"] = calendar_event_risk
            if calendar_event_risk == "high":
                result["trading_allowed"] = False

        result["calendar_source"] = calendar_source
        result["calendar_event_count"] = calendar_event_count
        return result

    def _parse_response(self, response: str) -> dict:
        """Parst die JSON-Antwort von Claude."""
        try:
            # JSON aus der Antwort extrahieren
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()

            parsed = json.loads(response)

            # Validierung
            macro_bias = parsed.get("macro_bias", "neutral")
            event_risk = parsed.get("event_risk", "medium")

            return {
                "macro_bias": macro_bias if macro_bias in ("bullish", "bearish", "neutral") else "neutral",
                "event_risk": event_risk if event_risk in ("low", "medium", "high") else "medium",
                "trading_allowed": bool(parsed.get("trading_allowed", True)),
                "key_themes": parsed.get("key_themes", []),
                "reasoning": parsed.get("reasoning", ""),
            }

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"JSON-Parsing fehlgeschlagen: {e} | Antwort: {response[:200]}")
            return self._default_result("", "JSON-Parsing-Fehler")

    def check_news_block(
        self,
        symbol: str,
        minutes_before: int = 30,
        minutes_after: int = 30,
    ) -> tuple[bool, str]:
        """
        Prüft ob ein News-Block für das Symbol aktiv ist (P1.4).

        Ein Block greift wenn ein High-Impact Event der relevanten Währung
        innerhalb von minutes_before Minuten bevorsteht ODER innerhalb von
        minutes_after Minuten stattgefunden hat.

        Args:
            symbol:         Trading-Symbol, z.B. "EURUSD"
            minutes_before: Sperrfenster vor dem Event
            minutes_after:  Sperrfenster nach dem Event

        Returns:
            (True,  "News-Block: <Titel> (<Währung>) in <N> Min")  → blockiert
            (False, "")                                             → frei
        """
        currencies = _extract_currencies(symbol)
        if not currencies:
            return False, ""

        try:
            from config import config as _cfg
            cal = EconomicCalendar(_cfg)
            all_events = cal.get_events(currencies)
        except Exception as e:
            self.logger.error(f"[MacroAgent] check_news_block Fehler: {e}")
            return False, ""

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=minutes_after)
        window_end = now + timedelta(minutes=minutes_before)

        for event in all_events:
            if event.get("currency") not in currencies:
                continue
            event_time = _parse_event_time(event.get("time", ""))
            if event_time == datetime.min.replace(tzinfo=timezone.utc):
                continue
            if window_start <= event_time <= window_end:
                delta_min = int((event_time - now).total_seconds() / 60)
                name = event.get("name", "Unbekanntes Event")
                if delta_min >= 0:
                    reason = f"News-Block: {name} ({event['currency']}) in {delta_min} Min"
                else:
                    reason = f"News-Block: {name} ({event['currency']}) vor {abs(delta_min)} Min"
                return True, reason

        return False, ""


    def get_risk_sentiment(self, vix_threshold: float = 25.0) -> str:
        """
        Ermittelt die aktuelle Risikobereitschaft am Markt über den VIX-Index.

        Logik:
          VIX >= vix_threshold           → "risk_off"
          VIX < vix_threshold * 0.75     → "risk_on"
          Dazwischen / Datenfehler       → "neutral"

        Args:
            vix_threshold: VIX-Schwellwert für Risk-Off (Standard: 20.0)

        Returns:
            "risk_on" | "risk_off" | "neutral"
        """
        try:
            import yfinance as yf  # lokaler Import – kein Pflicht-Dependency
            ticker = yf.Ticker("^VIX")
            hist = ticker.history(period="1d", interval="1d")
            if hist.empty:
                self.logger.warning("VIX-Daten nicht verfügbar – Sentiment: neutral")
                return "neutral"
            vix_close = float(hist["Close"].iloc[-1])
            self.logger.debug(f"VIX: {vix_close:.2f} (Schwellwert: {vix_threshold})")
            if vix_close >= vix_threshold:
                return "risk_off"
            if vix_close < vix_threshold * 0.75:
                return "risk_on"
            return "neutral"
        except Exception as e:
            self.logger.warning(f"VIX-Abruf fehlgeschlagen: {e} – Sentiment: neutral")
            return "neutral"

    def _default_result(self, symbol: str, reason: str) -> dict:
        """Standardergebnis bei fehlender Datengrundlage.
        trading_allowed richtet sich nach macro_unknown_risk_blocks_trading (config)."""
        try:
            from config import config as _cfg
            blocks = getattr(_cfg, "macro_unknown_risk_blocks_trading", True)
        except Exception:
            blocks = True

        trading_allowed = not blocks
        if symbol:
            if trading_allowed:
                self.logger.info(
                    f"Keine News für {symbol} – UNKNOWN Event-Risiko, Trading erlaubt "
                    f"(macro_unknown_risk_blocks_trading=false)"
                )
            else:
                self.logger.warning(
                    f"Keine News für {symbol} – UNKNOWN Event-Risiko blockiert Trading "
                    f"(macro_unknown_risk_blocks_trading=true)."
                )

        return {
            "macro_bias": "neutral",
            "event_risk": "unknown",
            "trading_allowed": trading_allowed,
            "key_themes": [],
            "reasoning": f"Standardwerte verwendet: {reason}",
            "symbol": symbol,
            "news_count": 0,
        }
