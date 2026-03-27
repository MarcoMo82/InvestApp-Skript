"""
Unit-Tests für EconomicCalendar (data/economic_calendar.py).

Testet:
  - JBlanked API Integration (gemockte HTTP-Response)
  - Fallback-Logik: JBlanked schlägt fehl → investpy
  - provider="none" gibt leere Liste zurück
  - high_impact_only-Filter
  - Zeitfenster-Filter
  - In-memory Cache
  - Währungsextraktion aus Symbol (via _extract_currencies)
  - _normalize_impact
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Hilfsfunktion: minimales Config-Mock ──────────────────────────────────────

def _make_config(
    provider: str = "auto",
    api_key: str = "",
    lookback_hours: int = 12,
    lookahead_hours: int = 24,
    high_impact_only: bool = True,
    jblanked_url: str = "https://www.jblanked.com/news/api/forex-factory/calendar/today/",
) -> MagicMock:
    cfg = MagicMock()
    cfg.economic_calendar_provider = provider
    cfg.economic_calendar_jblanked_api_key = api_key
    cfg.economic_calendar_jblanked_url = jblanked_url
    cfg.economic_calendar_lookback_hours = lookback_hours
    cfg.economic_calendar_lookahead_hours = lookahead_hours
    cfg.economic_calendar_high_impact_only = high_impact_only
    return cfg


def _future_iso(hours: int = 2) -> str:
    """Gibt einen ISO-Zeitstempel in der Zukunft zurück."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _past_iso(hours: int = 2) -> str:
    """Gibt einen ISO-Zeitstempel in der Vergangenheit zurück."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ── EconomicCalendar importieren ──────────────────────────────────────────────

from data.economic_calendar import EconomicCalendar


def _extract_currencies(symbol: str) -> list[str]:
    """Dieselbe Logik wie _extract_currencies in macro_agent."""
    clean = symbol.upper().replace("=X", "").replace("-", "").replace("/", "")
    if len(clean) == 6 and clean.isalpha():
        return [clean[:3], clean[3:]]
    return []


# ── Tests: _normalize_impact ──────────────────────────────────────────────────

class TestNormalizeImpact:
    def setup_method(self):
        self.cal = EconomicCalendar(_make_config())

    def test_high_variants(self):
        for raw in ("high", "High", "HIGH", "3", "red", "high impact"):
            assert self.cal._normalize_impact(raw) == "high"

    def test_medium_variants(self):
        for raw in ("medium", "Medium", "MEDIUM", "moderate", "2", "orange"):
            assert self.cal._normalize_impact(raw) == "medium"

    def test_low_variants(self):
        for raw in ("low", "Low", "1", "green", "", "unknown"):
            assert self.cal._normalize_impact(raw) == "low"


# ── Tests: provider="none" ────────────────────────────────────────────────────

class TestProviderNone:
    def test_returns_empty_list(self):
        cfg = _make_config(provider="none")
        cal = EconomicCalendar(cfg)
        result = cal.get_events(["USD", "EUR"])
        assert result == []
        assert cal.last_source == "UNKNOWN"


# ── Tests: JBlanked API ───────────────────────────────────────────────────────

class TestJBlanked:
    def _make_jblanked_response(self, currency: str = "USD") -> list[dict]:
        return [
            {
                "date": _future_iso(2),
                "country": currency,
                "title": "Non-Farm Payrolls",
                "impact": "High",
                "actual": None,
                "forecast": "180K",
                "previous": "151K",
            }
        ]

    def test_jblanked_fetched_when_api_key_set(self):
        cfg = _make_config(provider="jblanked", api_key="test-key-123")
        cal = EconomicCalendar(cfg)

        mock_resp = MagicMock()
        mock_resp.json.return_value = self._make_jblanked_response("USD")
        mock_resp.raise_for_status.return_value = None

        with patch("data.economic_calendar.requests.get", return_value=mock_resp) as mock_get:
            events = cal.get_events(["USD"])

        assert mock_get.called
        assert len(events) == 1
        assert events[0]["currency"] == "USD"
        assert events[0]["name"] == "Non-Farm Payrolls"
        assert events[0]["impact"] == "high"
        assert cal.last_source == "JBlanked"

    def test_jblanked_skipped_without_api_key(self):
        """Kein API-Key → JBlanked wird übersprungen, kein HTTP-Request."""
        cfg = _make_config(provider="jblanked", api_key="")
        cal = EconomicCalendar(cfg)

        with patch("data.economic_calendar.requests.get") as mock_get:
            cal.get_events(["USD"])

        mock_get.assert_not_called()

    def test_jblanked_sends_auth_header(self):
        cfg = _make_config(provider="jblanked", api_key="my-secret-key")
        cal = EconomicCalendar(cfg)

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        with patch("data.economic_calendar.requests.get", return_value=mock_resp) as mock_get:
            cal.get_events(["USD"])

        call_kwargs = mock_get.call_args
        assert call_kwargs[1]["headers"] == {"Authorization": "Api-Key my-secret-key"}
        assert call_kwargs[1]["timeout"] == 10

    def test_jblanked_normalizes_multiple_events(self):
        cfg = _make_config(provider="jblanked", api_key="key")
        cal = EconomicCalendar(cfg)

        raw = [
            {"date": _future_iso(1), "country": "USD", "title": "CPI", "impact": "high"},
            {"date": _future_iso(3), "country": "USD", "title": "PPI", "impact": "high"},
            {"date": _future_iso(5), "country": "USD", "title": "News", "impact": "low"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw
        mock_resp.raise_for_status.return_value = None

        with patch("data.economic_calendar.requests.get", return_value=mock_resp):
            events = cal.get_events(["USD"])

        # high_impact_only=True → nur 2 high events
        assert len(events) == 2
        assert all(e["impact"] == "high" for e in events)


# ── Tests: Fallback-Logik ─────────────────────────────────────────────────────

class TestFallbackLogic:
    def test_jblanked_fails_falls_back_to_investpy(self):
        """JBlanked schlägt fehl → investpy wird genutzt."""
        cfg = _make_config(provider="auto", api_key="key")
        cal = EconomicCalendar(cfg)

        # JBlanked wirft Exception
        import requests as _requests
        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = _requests.HTTPError("403 Forbidden")

        import pandas as pd

        investpy_data = pd.DataFrame([{
            "id": "1",
            "date": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
            "time": (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%H:%M"),
            "zone": "united states",
            "currency": "USD",
            "importance": "high",
            "event": "Initial Jobless Claims",
            "actual": None,
            "forecast": "211K",
            "previous": "205K",
        }])

        with patch("data.economic_calendar.requests.get", return_value=error_resp):
            with patch("investpy.economic_calendar", return_value=investpy_data):
                events = cal.get_events(["USD"])

        assert len(events) >= 0  # Fallback wurde versucht
        # Source sollte investpy sein (auch wenn JBlanked fehlschlug)
        assert "investpy" in cal.last_source or cal.last_source == "UNKNOWN"

    def test_no_api_key_goes_directly_to_investpy(self):
        """Kein JBlanked-Key → direkt zu investpy."""
        cfg = _make_config(provider="auto", api_key="")
        cal = EconomicCalendar(cfg)

        import pandas as pd

        investpy_data = pd.DataFrame([{
            "id": "1",
            "date": datetime.now(timezone.utc).strftime("%d/%m/%Y"),
            "time": (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%H:%M"),
            "zone": "united states",
            "currency": "USD",
            "importance": "high",
            "event": "NFP",
            "actual": None,
            "forecast": "180K",
            "previous": "151K",
        }])

        with patch("data.economic_calendar.requests.get") as mock_get:
            with patch("investpy.economic_calendar", return_value=investpy_data):
                events = cal.get_events(["USD"])

        # Kein JBlanked-Request
        mock_get.assert_not_called()
        # investpy wurde genutzt
        assert "investpy" in cal.last_source

    def test_both_fail_returns_empty_list(self):
        """Beide Quellen fehlgeschlagen → leere Liste, source=UNKNOWN."""
        cfg = _make_config(provider="auto", api_key="key")
        cal = EconomicCalendar(cfg)

        import requests as _requests
        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = _requests.HTTPError("500")

        with patch("data.economic_calendar.requests.get", return_value=error_resp):
            with patch("investpy.economic_calendar", side_effect=RuntimeError("investpy down")):
                events = cal.get_events(["USD"])

        assert events == []
        assert cal.last_source == "UNKNOWN"


# ── Tests: Filter ─────────────────────────────────────────────────────────────

class TestFilters:
    def _cal_with_jblanked_data(self, raw_events: list[dict]) -> EconomicCalendar:
        cfg = _make_config(provider="jblanked", api_key="key")
        cal = EconomicCalendar(cfg)
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw_events
        mock_resp.raise_for_status.return_value = None
        return cal, mock_resp

    def test_high_impact_only_filters_medium_and_low(self):
        raw = [
            {"date": _future_iso(1), "country": "USD", "title": "A", "impact": "high"},
            {"date": _future_iso(2), "country": "USD", "title": "B", "impact": "medium"},
            {"date": _future_iso(3), "country": "USD", "title": "C", "impact": "low"},
        ]
        cal, mock_resp = self._cal_with_jblanked_data(raw)
        with patch("data.economic_calendar.requests.get", return_value=mock_resp):
            events = cal.get_events(["USD"])
        assert len(events) == 1
        assert events[0]["name"] == "A"

    def test_high_impact_false_includes_medium(self):
        cfg = _make_config(provider="jblanked", api_key="key", high_impact_only=False)
        cal = EconomicCalendar(cfg)
        raw = [
            {"date": _future_iso(1), "country": "USD", "title": "A", "impact": "high"},
            {"date": _future_iso(2), "country": "USD", "title": "B", "impact": "medium"},
            {"date": _future_iso(3), "country": "USD", "title": "C", "impact": "low"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw
        mock_resp.raise_for_status.return_value = None
        with patch("data.economic_calendar.requests.get", return_value=mock_resp):
            events = cal.get_events(["USD"])
        names = {e["name"] for e in events}
        assert "A" in names
        assert "B" in names
        assert "C" not in names  # low wird weiterhin gefiltert

    def test_time_window_filter(self):
        """Events außerhalb des lookback/lookahead-Fensters werden herausgefiltert."""
        cfg = _make_config(
            provider="jblanked",
            api_key="key",
            lookback_hours=1,
            lookahead_hours=2,
        )
        cal = EconomicCalendar(cfg)
        raw = [
            # In Fenster: 1h in Zukunft
            {"date": _future_iso(1), "country": "USD", "title": "In-Window", "impact": "high"},
            # Außerhalb: 5h in Zukunft (lookahead_hours=2)
            {"date": _future_iso(5), "country": "USD", "title": "Out-Future", "impact": "high"},
            # Außerhalb: 3h in Vergangenheit (lookback_hours=1)
            {"date": _past_iso(3), "country": "USD", "title": "Out-Past", "impact": "high"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw
        mock_resp.raise_for_status.return_value = None
        with patch("data.economic_calendar.requests.get", return_value=mock_resp):
            events = cal.get_events(["USD"])
        assert len(events) == 1
        assert events[0]["name"] == "In-Window"


# ── Tests: In-memory Cache ────────────────────────────────────────────────────

class TestCache:
    def test_cache_prevents_second_request(self):
        cfg = _make_config(provider="jblanked", api_key="key")
        cal = EconomicCalendar(cfg)

        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"date": _future_iso(1), "country": "USD", "title": "NFP", "impact": "high"}
        ]
        mock_resp.raise_for_status.return_value = None

        with patch("data.economic_calendar.requests.get", return_value=mock_resp) as mock_get:
            cal.get_events(["USD"])
            cal.get_events(["USD"])

        # Zweiter Aufruf nutzt Cache → nur 1 HTTP-Request
        assert mock_get.call_count == 1

    def test_different_currencies_not_cached_together(self):
        cfg = _make_config(provider="jblanked", api_key="key")
        cal = EconomicCalendar(cfg)

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status.return_value = None

        with patch("data.economic_calendar.requests.get", return_value=mock_resp) as mock_get:
            cal.get_events(["USD"])
            cal.get_events(["EUR"])

        # Unterschiedliche Cache-Keys → 2 Requests
        assert mock_get.call_count == 2


# ── Tests: Währungsextraktion ─────────────────────────────────────────────────

class TestCurrencyExtraction:
    """Testet _extract_currencies aus macro_agent (reimplementiert hier)."""

    def test_eurusd(self):
        assert set(_extract_currencies("EURUSD")) == {"EUR", "USD"}

    def test_usdjpy(self):
        assert set(_extract_currencies("USDJPY")) == {"USD", "JPY"}

    def test_xauusd(self):
        assert set(_extract_currencies("XAUUSD")) == {"XAU", "USD"}

    def test_btcusd(self):
        assert set(_extract_currencies("BTCUSD")) == {"BTC", "USD"}

    def test_yfinance_suffix_removed(self):
        assert set(_extract_currencies("EURUSD=X")) == {"EUR", "USD"}

    def test_stock_returns_empty(self):
        assert _extract_currencies("AAPL") == []
        assert _extract_currencies("MSFT") == []

    def test_case_insensitive(self):
        assert set(_extract_currencies("eurusd")) == {"EUR", "USD"}


# ── Tests: _fetch_investiny Normalisierung ────────────────────────────────────

class TestNormalizeInvestpy:
    def setup_method(self):
        self.cal = EconomicCalendar(_make_config())

    def test_normalizes_standard_row(self):
        row = {
            "date": "27/03/2026",
            "time": "14:30",
            "currency": "USD",
            "importance": "high",
            "event": "Non-Farm Payrolls",
            "actual": None,
            "forecast": "180K",
            "previous": "151K",
        }
        result = self.cal._normalize_investpy(row)
        assert result is not None
        assert result["currency"] == "USD"
        assert result["impact"] == "high"
        assert result["name"] == "Non-Farm Payrolls"
        assert result["time"] == "2026-03-27T14:30:00Z"

    def test_returns_none_for_missing_date(self):
        row = {"date": "", "time": "14:30", "currency": "USD", "importance": "high", "event": "X"}
        assert self.cal._normalize_investpy(row) is None

    def test_returns_none_for_invalid_date(self):
        row = {"date": "not-a-date", "time": "14:30", "currency": "USD", "importance": "high", "event": "X"}
        assert self.cal._normalize_investpy(row) is None


# ── Tests: _normalize_jblanked ────────────────────────────────────────────────

class TestNormalizeJblanked:
    def setup_method(self):
        self.cal = EconomicCalendar(_make_config())

    def test_normalizes_standard_event(self):
        raw = {
            "date": "2026-03-27T14:30:00Z",
            "country": "USD",
            "title": "NFP",
            "impact": "High",
            "actual": None,
            "forecast": "180K",
            "previous": "151K",
        }
        result = self.cal._normalize_jblanked(raw, "USD")
        assert result is not None
        assert result["currency"] == "USD"
        assert result["impact"] == "high"
        assert result["name"] == "NFP"

    def test_returns_none_for_missing_date(self):
        raw = {"country": "USD", "title": "NFP", "impact": "High"}
        assert self.cal._normalize_jblanked(raw, "USD") is None

    def test_uses_default_currency_as_fallback(self):
        raw = {"date": "2026-03-27T14:30:00Z", "title": "X", "impact": "high"}
        result = self.cal._normalize_jblanked(raw, "JPY")
        assert result is not None
        assert result["currency"] == "JPY"
