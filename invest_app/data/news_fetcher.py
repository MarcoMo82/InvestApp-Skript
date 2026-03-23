"""
News Fetcher für Yahoo Finance und Finanz-Nachrichtenquellen.
Beinhaltet Caching mit 5-Minuten TTL.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 300  # 5 Minuten


class _CacheEntry:
    def __init__(self, data: list[dict]) -> None:
        self.data = data
        self.timestamp = time.monotonic()

    def is_valid(self) -> bool:
        return (time.monotonic() - self.timestamp) < CACHE_TTL_SECONDS


class NewsFetcher:
    """
    Holt und cached Finanznachrichten aus Yahoo Finance und anderen Quellen.
    Unterstützt symbol-spezifische und allgemeine Marktnachrichten.
    """

    def __init__(self) -> None:
        self._cache: dict[str, _CacheEntry] = {}

    def get_yahoo_news(self, symbol: str) -> list[dict]:
        """
        Holt aktuelle Nachrichten für ein Symbol von Yahoo Finance.

        Args:
            symbol: Ticker-Symbol, z.B. 'AAPL', 'BTC-USD'

        Returns:
            Liste von Nachrichten-Dicts mit: title, publisher, link, published_at, summary
        """
        cache_key = f"yahoo_{symbol}"
        cached = self._cache.get(cache_key)
        if cached and cached.is_valid():
            logger.debug(f"News-Cache Hit: {cache_key}")
            return cached.data

        try:
            ticker = yf.Ticker(symbol)
            raw_news = ticker.news or []
            news = []

            for item in raw_news[:10]:  # Maximal 10 Artikel
                content = item.get("content", {})
                title = content.get("title", item.get("title", ""))
                publisher = (
                    content.get("provider", {}).get("displayName", "")
                    or item.get("publisher", "")
                )
                link = (
                    content.get("canonicalUrl", {}).get("url", "")
                    or item.get("link", "")
                )

                pub_date_raw = content.get("pubDate", item.get("providerPublishTime", 0))
                if isinstance(pub_date_raw, str):
                    try:
                        pub_date = datetime.fromisoformat(pub_date_raw.replace("Z", "+00:00"))
                    except ValueError:
                        pub_date = datetime.now(timezone.utc)
                elif isinstance(pub_date_raw, (int, float)) and pub_date_raw > 0:
                    pub_date = datetime.fromtimestamp(pub_date_raw, tz=timezone.utc)
                else:
                    pub_date = datetime.now(timezone.utc)

                summary = content.get("summary", item.get("summary", ""))

                if title:
                    news.append({
                        "title": title,
                        "publisher": publisher,
                        "link": link,
                        "published_at": pub_date.isoformat(),
                        "summary": summary,
                        "source": "yahoo_finance",
                        "symbol": symbol,
                    })

            self._cache[cache_key] = _CacheEntry(news)
            logger.info(f"Yahoo News geladen: {symbol} | {len(news)} Artikel")
            return news

        except Exception as e:
            logger.error(f"Yahoo News Fehler für {symbol}: {e}")
            return []

    def get_finanznachrichten(self, query: str = "forex trading") -> list[dict]:
        """
        Holt allgemeine Marktnachrichten von finviz oder ähnlichen Quellen via RSS/Scraping.
        Fallback auf Yahoo Finance Market News.

        Args:
            query: Suchbegriff für die News-Anfrage

        Returns:
            Liste von Nachrichten-Dicts
        """
        cache_key = f"markt_{query}"
        cached = self._cache.get(cache_key)
        if cached and cached.is_valid():
            logger.debug(f"News-Cache Hit: {cache_key}")
            return cached.data

        news = self._fetch_yahoo_market_news(query)

        self._cache[cache_key] = _CacheEntry(news)
        return news

    def get_economic_calendar_summary(self) -> str:
        """
        Gibt eine einfache Zusammenfassung wichtiger heutiger Wirtschaftsereignisse zurück.
        Nutzt Yahoo Finance als Datenquelle.

        Returns:
            Textuelle Zusammenfassung des Wirtschaftskalenders
        """
        # Holt News für wichtige Währungspaare als Proxy für Makro-Events
        all_news = []
        for symbol in ["EURUSD=X", "USDJPY=X", "^DXY"]:
            all_news.extend(self.get_yahoo_news(symbol))

        if not all_news:
            return "Keine Wirtschaftsnachrichten verfügbar."

        titles = [n["title"] for n in all_news[:5]]
        summary = "Aktuelle Markt-Nachrichten:\n" + "\n".join(f"- {t}" for t in titles)
        return summary

    def _fetch_yahoo_market_news(self, query: str) -> list[dict]:
        """Holt allgemeine Marktnachrichten über Yahoo Finance."""
        try:
            # Nutze SPY als Proxy für allgemeine Marktnachrichten
            symbols = ["SPY", "GLD", "^VIX"] if "market" in query.lower() else ["EURUSD=X"]
            all_news: list[dict] = []

            for sym in symbols:
                all_news.extend(self.get_yahoo_news(sym))

            # Deduplizieren nach Titel
            seen: set[str] = set()
            unique_news = []
            for item in all_news:
                if item["title"] not in seen:
                    seen.add(item["title"])
                    unique_news.append(item)

            logger.info(f"Markt-News geladen: {len(unique_news)} eindeutige Artikel")
            return unique_news[:15]

        except Exception as e:
            logger.error(f"Fehler beim Laden der Markt-News: {e}")
            return []

    def clear_cache(self) -> None:
        """Leert den gesamten News-Cache."""
        self._cache.clear()
        logger.debug("News-Cache geleert.")

    def cache_stats(self) -> dict:
        """Gibt Cache-Statistiken zurück."""
        valid = sum(1 for e in self._cache.values() if e.is_valid())
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid,
            "expired_entries": len(self._cache) - valid,
        }
