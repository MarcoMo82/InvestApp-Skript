"""
Tests für NewsFetcher – persistenter Disk-Cache + in-memory Cache.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import Config
from data.news_fetcher import NewsFetcher, CACHE_FILE, CACHE_TTL_SECONDS


SAMPLE_ARTICLES = [
    {
        "title": "Test News 1",
        "publisher": "Reuters",
        "link": "https://example.com/1",
        "published_at": "2026-03-23T10:00:00+00:00",
        "summary": "Test summary",
        "source": "yahoo_finance",
        "symbol": "AAPL",
    }
]


@pytest.fixture(autouse=True)
def clean_disk_cache(tmp_path, monkeypatch):
    """Leitet CACHE_FILE auf ein temporäres Verzeichnis um und räumt danach auf."""
    tmp_cache = tmp_path / "news_cache.json"
    monkeypatch.setattr("data.news_fetcher.CACHE_FILE", tmp_cache)
    yield tmp_cache


def _cfg(yahoo_enabled: bool = True) -> Config:
    """Erzeugt eine Config mit angepasstem news_yahoo_enabled."""
    cfg = Config.__new__(Config)
    # Felder direkt setzen ohne __post_init__ auszulösen
    import copy
    cfg = copy.copy(Config())
    cfg.news_yahoo_enabled = yahoo_enabled
    return cfg


def _make_fetcher_with_api_mock(articles=None, yahoo_enabled: bool = True):
    """Gibt einen NewsFetcher zurück, dessen yfinance-Aufruf gemockt ist."""
    if articles is None:
        articles = SAMPLE_ARTICLES

    fetcher = NewsFetcher(cfg=_cfg(yahoo_enabled=yahoo_enabled))

    # Simuliere yfinance-Rückgabe
    mock_ticker = MagicMock()
    mock_ticker.news = [
        {
            "content": {
                "title": a["title"],
                "provider": {"displayName": a["publisher"]},
                "canonicalUrl": {"url": a["link"]},
                "pubDate": a["published_at"],
                "summary": a["summary"],
            }
        }
        for a in articles
    ]
    return fetcher, mock_ticker


# ---------------------------------------------------------------------------
# 1. Cache-Datei wird nach erstem Laden angelegt
# ---------------------------------------------------------------------------
def test_disk_cache_created_after_first_fetch(clean_disk_cache):
    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = fetcher.get_yahoo_news("AAPL")

    assert len(result) == len(SAMPLE_ARTICLES)
    assert clean_disk_cache.exists(), "Disk-Cache-Datei sollte nach erstem Fetch existieren"

    data = json.loads(clean_disk_cache.read_text(encoding="utf-8"))
    assert "news_AAPL" in data
    assert "timestamp" in data["news_AAPL"]
    assert "articles" in data["news_AAPL"]


# ---------------------------------------------------------------------------
# 2. Zweiter Aufruf liest aus Cache – kein weiterer API-Call
# ---------------------------------------------------------------------------
def test_second_call_uses_disk_cache(clean_disk_cache):
    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        fetcher.get_yahoo_news("AAPL")  # Erster Aufruf → API
        # In-memory löschen, damit Schicht 2 greift
        fetcher._cache.clear()
        result = fetcher.get_yahoo_news("AAPL")  # Zweiter Aufruf → Disk-Cache

    assert mock_yf.call_count == 1, "yfinance.Ticker sollte nur einmal aufgerufen worden sein"
    assert len(result) == len(SAMPLE_ARTICLES)


# ---------------------------------------------------------------------------
# 3. Cache gilt als ungültig nach > 60 Minuten (Timestamp manipulieren)
# ---------------------------------------------------------------------------
def test_expired_disk_cache_triggers_new_fetch(clean_disk_cache):
    # Schreibe einen abgelaufenen Cache manuell
    old_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=CACHE_TTL_SECONDS + 60)).isoformat()
    expired_cache = {
        "news_AAPL": {
            "timestamp": old_timestamp,
            "articles": SAMPLE_ARTICLES,
        }
    }
    clean_disk_cache.write_text(json.dumps(expired_cache), encoding="utf-8")

    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        result = fetcher.get_yahoo_news("AAPL")

    assert mock_yf.call_count == 1, "API sollte bei abgelaufenem Cache aufgerufen werden"
    assert len(result) == len(SAMPLE_ARTICLES)

    # Cache-Datei sollte neuen Timestamp haben
    updated = json.loads(clean_disk_cache.read_text(encoding="utf-8"))
    new_ts = datetime.fromisoformat(updated["news_AAPL"]["timestamp"])
    age = datetime.now(timezone.utc) - new_ts
    assert age.total_seconds() < 10, "Neuer Timestamp sollte aktuell sein"


# ---------------------------------------------------------------------------
# 4. Korrupte Cache-Datei → Fallback auf API
# ---------------------------------------------------------------------------
def test_corrupt_cache_falls_back_to_api(clean_disk_cache):
    clean_disk_cache.write_text("{ ungültiges json }", encoding="utf-8")

    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        result = fetcher.get_yahoo_news("AAPL")

    assert mock_yf.call_count == 1, "API-Fallback bei korruptem Cache erwartet"
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 5. Fehlende Cache-Datei → Fallback auf API
# ---------------------------------------------------------------------------
def test_missing_cache_file_falls_back_to_api(clean_disk_cache):
    # Datei existiert nicht (autouse-Fixture stellt sicher, dass sie nicht existiert)
    assert not clean_disk_cache.exists()

    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        result = fetcher.get_yahoo_news("AAPL")

    assert mock_yf.call_count == 1
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 6. cache_stats enthält Disk-Infos
# ---------------------------------------------------------------------------
def test_cache_stats_includes_disk(clean_disk_cache):
    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker):
        fetcher.get_yahoo_news("AAPL")

    stats = fetcher.cache_stats()
    assert "disk_total" in stats
    assert "disk_valid" in stats
    assert stats["disk_total"] >= 1
    assert stats["disk_valid"] >= 1


# ---------------------------------------------------------------------------
# 7. clear_cache(disk=True) löscht auch die Datei
# ---------------------------------------------------------------------------
def test_clear_cache_with_disk_flag(clean_disk_cache):
    fetcher, mock_ticker = _make_fetcher_with_api_mock()

    with patch("yfinance.Ticker", return_value=mock_ticker):
        fetcher.get_yahoo_news("AAPL")

    assert clean_disk_cache.exists()
    fetcher.clear_cache(disk=True)
    assert not clean_disk_cache.exists()
    assert len(fetcher._cache) == 0


# ---------------------------------------------------------------------------
# 8. NEWS_YAHOO_ENABLED=False → get_yahoo_news gibt leere Liste zurück (kein API-Call)
# ---------------------------------------------------------------------------
def test_yahoo_disabled_returns_empty_list(clean_disk_cache):
    fetcher, mock_ticker = _make_fetcher_with_api_mock(yahoo_enabled=False)

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        result = fetcher.get_yahoo_news("AAPL")

    assert result == [], "Deaktivierte Yahoo-API muss leere Liste zurückgeben"
    mock_yf.assert_not_called()


# ---------------------------------------------------------------------------
# 9. NEWS_YAHOO_ENABLED=False → get_finanznachrichten gibt leere Liste zurück
# ---------------------------------------------------------------------------
def test_finanznachrichten_disabled_returns_empty_list(clean_disk_cache):
    fetcher, mock_ticker = _make_fetcher_with_api_mock(yahoo_enabled=False)

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_yf:
        result = fetcher.get_finanznachrichten("forex")

    assert result == [], "Deaktivierte Yahoo-API muss leere Liste zurückgeben"
    mock_yf.assert_not_called()
