"""
Makro-Agent: Analysiert Makro-Umfeld und News mit Claude LLM.
Output: macro_bias, event_risk, trading_allowed, reasoning
"""

from __future__ import annotations

import json
from typing import Any

from typing import Any

from agents.base_agent import BaseAgent
from utils.claude_client import ClaudeClient
from data.news_fetcher import NewsFetcher

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
            macro_bias, event_risk, trading_allowed, key_themes, reasoning
        """
        symbol = self._require_field(data, "symbol")

        # News holen (Yahoo Finance + MT5 falls verfügbar)
        news_items = self.news_fetcher.get_yahoo_news(symbol)
        market_news = self.news_fetcher.get_finanznachrichten()
        mt5_news = (
            self.data_connector.get_news(hours_back=4)
            if hasattr(self, "data_connector") and hasattr(self.data_connector, "get_news")
            else []
        )

        all_news = (news_items + market_news + mt5_news)[:10]

        if not all_news:
            self.logger.warning(f"Keine News für {symbol} – Makro-Analyse mit Standardwerten.")
            return self._default_result(symbol, "Keine News verfügbar.")

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
            return self._default_result(symbol, str(e))

        result["symbol"] = symbol
        result["news_count"] = len(all_news)
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

    @staticmethod
    def _default_result(symbol: str, reason: str) -> dict:
        return {
            "macro_bias": "neutral",
            "event_risk": "medium",
            "trading_allowed": True,
            "key_themes": [],
            "reasoning": f"Standardwerte verwendet: {reason}",
            "symbol": symbol,
            "news_count": 0,
        }
