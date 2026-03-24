"""
News Fetcher für Yahoo Finance und Finanz-Nachrichtenquellen.
Beinhaltet zweistufiges Caching: in-memory (session) + persistenter JSON-Cache auf Disk.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from config import Config, config as _default_config
from utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 3600  # 60 Minuten
CACHE_FILE = Path(__file__).parent.parent / "Output" / "news_cache.json"


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
    Zweistufiger Cache: in-memory (verhindert mehrfache Disk-Reads) + Disk (überlebt Neustart).
    """

    def __init__(self, cfg: Config | None = None) -> None:
        self.config = cfg or _default_config
        self._cache: dict[str, _CacheEntry] = {}
        yahoo_status = "aktiv" if self.config.news_yahoo_enabled else "deaktiviert"
        logger.info(f"[News] Quelle: MetaTrader 5 | Yahoo-API: {yahoo_status}")

    def _load_disk_cache(self) -> dict:
        """Lädt den persistenten Cache von Disk."""
        if not CACHE_FILE.exists():
            return {}
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_disk_cache(self, cache: dict) -> None:
        """Speichert den Cache auf Disk."""
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Disk-Cache konnte nicht gespeichert werden: {e}")

    def _is_disk_cache_valid(self, cache_entry: dict) -> bool:
        """Prüft ob ein Disk-Cache-Eintrag noch gültig ist (< 60 Minuten alt)."""
        if "timestamp" not in cache_entry:
            return False
        try:
            cached_at = datetime.fromisoformat(cache_entry["timestamp"])
            age = datetime.now(timezone.utc) - cached_at
            return age.total_seconds() < CACHE_TTL_SECONDS
        except Exception:
            return False

    def get_yahoo_news(self, symbol: str) -> list[dict]:
        """
        Holt aktuelle Nachrichten für ein Symbol von Yahoo Finance.
        Prüft zuerst in-memory Cache, dann Disk-Cache, dann API.

        Args:
            symbol: Ticker-Symbol, z.B. 'AAPL', 'BTC-USD'

        Returns:
            Liste von Nachrichten-Dicts mit: title, publisher, link, published_at, summary
        """
        if not self.config.news_yahoo_enabled:
            logger.debug("[News] Yahoo/externe API deaktiviert (NEWS_YAHOO_ENABLED=False)")
            return []

        cache_key = f"yahoo_{symbol}"

        # Schicht 1: in-memory Cache (verhindert mehrfache Disk-Reads in derselben Session)
        cached = self._cache.get(cache_key)
        if cached and cached.is_valid():
            logger.debug(f"News-Cache Hit (memory): {cache_key}")
            return cached.data

        # Schicht 2: Disk-Cache (überlebt App-Neustart)
        disk_cache = self._load_disk_cache()
        disk_key = f"news_{symbol}"
        if disk_key in disk_cache and self._is_disk_cache_valid(disk_cache[disk_key]):
            articles = disk_cache[disk_key]["articles"]
            age_min = int(
                (datetime.now(timezone.utc) - datetime.fromisoformat(disk_cache[disk_key]["timestamp"]))
                .total_seconds() / 60
            )
            logger.info(f"News aus Disk-Cache: {symbol} | Alter: {age_min} Min")
            self._cache[cache_key] = _CacheEntry(articles)
            return articles

        # Schicht 3: API-Aufruf
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

            # In beide Caches schreiben
            self._cache[cache_key] = _CacheEntry(news)
            disk_cache[disk_key] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "articles": news,
            }
            self._save_disk_cache(disk_cache)
            logger.info(f"Yahoo News geladen und gecacht: {symbol} | {len(news)} Artikel")
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
        if not self.config.news_yahoo_enabled:
            logger.debug("[News] Yahoo/externe API deaktiviert (NEWS_YAHOO_ENABLED=False)")
            return []

        cache_key = f"markt_{query}"

        # Schicht 1: in-memory
        cached = self._cache.get(cache_key)
        if cached and cached.is_valid():
            logger.debug(f"News-Cache Hit (memory): {cache_key}")
            return cached.data

        # Schicht 2: Disk-Cache
        disk_cache = self._load_disk_cache()
        disk_key = f"markt_{query}"
        if disk_key in disk_cache and self._is_disk_cache_valid(disk_cache[disk_key]):
            articles = disk_cache[disk_key]["articles"]
            age_min = int(
                (datetime.now(timezone.utc) - datetime.fromisoformat(disk_cache[disk_key]["timestamp"]))
                .total_seconds() / 60
            )
            logger.info(f"Markt-News aus Disk-Cache: {query} | Alter: {age_min} Min")
            self._cache[cache_key] = _CacheEntry(articles)
            return articles

        # Schicht 3: Neu laden
        news = self._fetch_yahoo_market_news(query)
        self._cache[cache_key] = _CacheEntry(news)
        disk_cache[disk_key] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "articles": news,
        }
        self._save_disk_cache(disk_cache)
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

    def clear_cache(self, disk: bool = False) -> None:
        """Leert den News-Cache. Mit disk=True auch die persistente Cache-Datei."""
        self._cache.clear()
        if disk and CACHE_FILE.exists():
            try:
                CACHE_FILE.unlink()
                logger.debug("Disk-Cache gelöscht.")
            except Exception as e:
                logger.warning(f"Disk-Cache konnte nicht gelöscht werden: {e}")
        logger.debug("In-Memory News-Cache geleert.")

    def cache_stats(self) -> dict:
        """Gibt Cache-Statistiken zurück (memory + disk)."""
        valid = sum(1 for e in self._cache.values() if e.is_valid())
        disk_cache = self._load_disk_cache()
        disk_valid = sum(1 for v in disk_cache.values() if self._is_disk_cache_valid(v))
        return {
            "memory_total": len(self._cache),
            "memory_valid": valid,
            "memory_expired": len(self._cache) - valid,
            "disk_total": len(disk_cache),
            "disk_valid": disk_valid,
            "disk_expired": len(disk_cache) - disk_valid,
            "disk_cache_file": str(CACHE_FILE),
        }
