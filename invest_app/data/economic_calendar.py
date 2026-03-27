"""
Wirtschaftskalender – holt High-Impact Events aus konfigurierten Quellen.
Fallback-Kette: JBlanked API → investpy/investiny (scrapet investing.com) → UNKNOWN

Quellen:
  1. JBlanked API  – wenn ``economic_calendar_jblanked_api_key`` gesetzt ist
  2. investpy      – kostenfrei, scrapet investing.com (kein API-Key nötig)
  3. UNKNOWN       – beide Quellen nicht erreichbar
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from utils.logger import get_logger

logger = get_logger(__name__)

_REQUEST_TIMEOUT = 10  # Sekunden
_JBLANKED_RATE_LIMIT_SECONDS = 1.0  # Rate-Limit JBlanked: max. 1 Request/Sekunde

# Mapping Währungscode → Ländername für investpy/investiny
_CURRENCY_TO_COUNTRY: dict[str, str] = {
    "USD": "united states",
    "EUR": "euro zone",
    "GBP": "united kingdom",
    "JPY": "japan",
    "CHF": "switzerland",
    "AUD": "australia",
    "CAD": "canada",
    "NZD": "new zealand",
    "CNY": "china",
    "MXN": "mexico",
}


class EconomicCalendar:
    """
    Wirtschaftskalender mit konfigurierbarer Fallback-Kette.

    Fallback-Reihenfolge (provider="auto"):
      1. JBlanked API  (nur wenn api_key gesetzt)
      2. investpy      (scrapet investing.com, kein Key nötig)
      3. UNKNOWN       (beide Quellen fehlgeschlagen)

    Attributes:
        last_source: Label der zuletzt genutzten Quelle (für Verbose-Ausgabe).
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        # In-memory Cache: cache_key → (source_label, events_list)
        self._cache: dict[str, tuple[str, list[dict]]] = {}
        self._last_jblanked_request: float = 0.0
        self.last_source: str = "UNKNOWN"

    def get_events(self, currencies: list[str]) -> list[dict]:
        """
        Holt Events für die angegebenen Währungen.

        Args:
            currencies: Liste von Währungscodes, z.B. ["USD", "EUR"]

        Returns:
            Liste von Event-Dicts:
            {
                "time": "2026-03-27T14:30:00Z",
                "currency": "USD",
                "name": "Non-Farm Payrolls",
                "impact": "high",      # high / medium / low
                "actual": None,        # None wenn noch nicht veröffentlicht
                "forecast": "180K",
                "previous": "151K"
            }
        """
        provider = getattr(self._config, "economic_calendar_provider", "auto")

        if provider == "none":
            self.last_source = "UNKNOWN"
            return []

        # Cache-Key: Datum + Währungen (sortiert für Konsistenz)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cache_key = f"{today}:{','.join(sorted(currencies))}"

        if cache_key in self._cache:
            source, events = self._cache[cache_key]
            self.last_source = source
            return events

        events: list[dict] = []
        source = "UNKNOWN"

        # ── Quelle 1: JBlanked API ───────────────────────────────────────────
        if provider in ("auto", "jblanked"):
            api_key = getattr(self._config, "economic_calendar_jblanked_api_key", "")
            if api_key:
                try:
                    events = self._fetch_jblanked(currencies)
                    source = "JBlanked"
                    logger.info(
                        f"[EconomicCalendar] JBlanked: {len(events)} Roh-Events geladen."
                    )
                except Exception as e:
                    logger.warning(f"[EconomicCalendar] JBlanked fehlgeschlagen: {e}")

        # ── Quelle 2: investpy (investing.com) ───────────────────────────────
        if not events and provider in ("auto", "investiny"):
            try:
                events = self._fetch_investiny(currencies)
                source = "investing.com via investpy"
                logger.info(
                    f"[EconomicCalendar] investpy: {len(events)} Roh-Events geladen."
                )
            except Exception as e:
                logger.warning(f"[EconomicCalendar] investpy fehlgeschlagen: {e}")
                source = "UNKNOWN"

        # ── Impact-Filter ────────────────────────────────────────────────────
        high_impact_only = getattr(self._config, "economic_calendar_high_impact_only", True)
        if high_impact_only:
            events = [e for e in events if e.get("impact", "").lower() == "high"]
        else:
            # importance >= medium
            events = [
                e for e in events
                if e.get("impact", "").lower() in ("high", "medium")
            ]

        # ── Zeitfenster-Filter ───────────────────────────────────────────────
        lookback_hours: int = getattr(self._config, "economic_calendar_lookback_hours", 12)
        lookahead_hours: int = getattr(self._config, "economic_calendar_lookahead_hours", 24)
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=lookback_hours)
        window_end = now + timedelta(hours=lookahead_hours)

        filtered: list[dict] = []
        for event in events:
            try:
                event_time = datetime.fromisoformat(
                    event["time"].replace("Z", "+00:00")
                )
                if window_start <= event_time <= window_end:
                    filtered.append(event)
            except (ValueError, KeyError) as exc:
                logger.debug(f"[EconomicCalendar] Ungültiges Event-Datum übersprungen: {exc}")

        events = filtered

        # In Cache schreiben
        self._cache[cache_key] = (source, events)
        self.last_source = source

        if events:
            logger.info(
                f"[EconomicCalendar] {len(events)} Event(s) via {source} "
                f"im Fenster -{lookback_hours}h/+{lookahead_hours}h."
            )
        else:
            logger.debug(
                f"[EconomicCalendar] Keine Events im Fenster "
                f"(Quelle: {source}, Währungen: {currencies})."
            )

        return events

    # ──────────────────────────────────────────────────────────────────────────
    # Private: JBlanked
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_jblanked(self, currencies: list[str]) -> list[dict]:
        """Holt Events von der JBlanked API (1 Request pro Währung, rate-limited)."""
        api_key = getattr(self._config, "economic_calendar_jblanked_api_key", "")
        if not api_key:
            raise ValueError("Kein JBlanked API-Key konfiguriert.")

        url: str = getattr(
            self._config,
            "economic_calendar_jblanked_url",
            "https://www.jblanked.com/news/api/forex-factory/calendar/today/",
        )
        headers = {"Authorization": f"Api-Key {api_key}"}

        all_events: list[dict] = []
        for currency in currencies:
            # Rate-Limit einhalten
            elapsed = time.monotonic() - self._last_jblanked_request
            if elapsed < _JBLANKED_RATE_LIMIT_SECONDS:
                time.sleep(_JBLANKED_RATE_LIMIT_SECONDS - elapsed)

            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    params={"currency": currency},
                    timeout=_REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                raw_list = resp.json()
            finally:
                self._last_jblanked_request = time.monotonic()

            for raw in (raw_list if isinstance(raw_list, list) else []):
                event = self._normalize_jblanked(raw, currency)
                if event:
                    all_events.append(event)

        return all_events

    def _normalize_jblanked(self, raw: dict, default_currency: str) -> dict | None:
        """Normalisiert ein JBlanked-Event in das Standard-Format."""
        date_str = raw.get("date", raw.get("time", ""))
        if not date_str:
            return None

        try:
            event_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            time_iso = event_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

        return {
            "time": time_iso,
            "currency": raw.get("country", raw.get("currency", default_currency)).upper(),
            "name": raw.get("title", raw.get("name", "Unbekanntes Event")),
            "impact": self._normalize_impact(raw.get("impact", "")),
            "actual": raw.get("actual") or None,
            "forecast": str(raw.get("forecast", "") or ""),
            "previous": str(raw.get("previous", "") or ""),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Private: investpy / investiny
    # ──────────────────────────────────────────────────────────────────────────

    def _fetch_investiny(self, currencies: list[str]) -> list[dict]:
        """
        Holt Events via investpy (scrapet investing.com).

        Versucht zuerst ``investiny.economic_calendar``, fällt auf
        ``investpy.economic_calendar`` zurück falls nicht verfügbar.
        """
        # Versuche investiny (neuere, leichtgewichtige Version)
        _economic_calendar = None
        try:
            from investiny import economic_calendar as _ec  # type: ignore[import]
            _economic_calendar = _ec
        except (ImportError, AttributeError):
            pass

        # Fallback auf investpy (vollständige Library)
        if _economic_calendar is None:
            try:
                from investpy import economic_calendar as _ec  # type: ignore[import]
                _economic_calendar = _ec
            except ImportError as exc:
                raise ImportError(
                    "Weder investiny noch investpy mit economic_calendar verfügbar. "
                    "Bitte installieren: pip install investpy"
                ) from exc

        # Währungen → Ländernamen
        countries = list({
            _CURRENCY_TO_COUNTRY[c]
            for c in currencies
            if c in _CURRENCY_TO_COUNTRY
        })
        if not countries:
            logger.debug(
                "[EconomicCalendar] Keine bekannten Länder für Währungen: %s",
                currencies,
            )
            return []

        lookback_hours: int = getattr(self._config, "economic_calendar_lookback_hours", 12)
        lookahead_hours: int = getattr(self._config, "economic_calendar_lookahead_hours", 24)
        now = datetime.now(timezone.utc)
        from_dt = now - timedelta(hours=lookback_hours)
        to_dt = now + timedelta(hours=lookahead_hours)

        # investpy erwartet DD/MM/YYYY
        from_date = from_dt.strftime("%d/%m/%Y")
        to_date = to_dt.strftime("%d/%m/%Y")

        try:
            df = _economic_calendar(
                countries=countries,
                importances=["high", "medium"],
                from_date=from_date,
                to_date=to_date,
            )
        except Exception as exc:
            raise RuntimeError(
                f"economic_calendar-Aufruf fehlgeschlagen: {exc}"
            ) from exc

        events: list[dict] = []
        for _, row in df.iterrows():
            event = self._normalize_investpy(row)
            if event:
                events.append(event)

        return events

    def _normalize_investpy(self, row: Any) -> dict | None:
        """Normalisiert eine investpy DataFrame-Zeile in das Standard-Format."""
        date_str = str(row.get("date", "") or "").strip()
        time_str = str(row.get("time", "00:00") or "00:00").strip()

        if not date_str:
            return None

        try:
            combined = f"{date_str} {time_str}"
            dt = datetime.strptime(combined, "%d/%m/%Y %H:%M")
            dt = dt.replace(tzinfo=timezone.utc)
            time_iso = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

        currency = str(row.get("currency", "") or "").upper().strip()
        importance = str(row.get("importance", "") or "").lower().strip()

        return {
            "time": time_iso,
            "currency": currency,
            "name": str(row.get("event", "Unbekanntes Event") or "Unbekanntes Event"),
            "impact": self._normalize_impact(importance),
            "actual": row.get("actual") or None,
            "forecast": str(row.get("forecast", "") or ""),
            "previous": str(row.get("previous", "") or ""),
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Hilfsfunktion
    # ──────────────────────────────────────────────────────────────────────────

    def _normalize_impact(self, raw: str) -> str:
        """Normalisiert verschiedene Impact-Darstellungen → high / medium / low."""
        if not raw:
            return "low"
        raw_lower = raw.lower().strip()
        if raw_lower in ("high", "3", "red", "high impact"):
            return "high"
        if raw_lower in ("medium", "moderate", "2", "orange"):
            return "medium"
        return "low"


# ── Rückwärtskompatible Funktion (Legacy-Aufruf aus macro_agent) ─────────────

def get_upcoming_high_impact_events(
    minutes_before: int = 30,
    minutes_after: int = 30,
) -> list[dict]:
    """
    Rückwärtskompatibel – gibt High-Impact Events im Zeitfenster zurück.

    Returns:
        Liste von {"time": datetime, "currency": str, "impact": str, "title": str}
        Leere Liste wenn API nicht erreichbar.
    """
    try:
        from config import config as _cfg  # type: ignore[import]
    except ImportError:
        return []

    try:
        cal = EconomicCalendar(_cfg)
        all_currencies = list(_CURRENCY_TO_COUNTRY.keys())
        raw_events = cal.get_events(all_currencies)
    except Exception as exc:
        logger.warning(
            f"[EconomicCalendar] get_upcoming_high_impact_events fehlgeschlagen: {exc}"
        )
        return []

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=minutes_after)
    window_end = now + timedelta(minutes=minutes_before)

    result: list[dict] = []
    for event in raw_events:
        try:
            event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00"))
            if window_start <= event_time <= window_end:
                result.append({
                    "time": event_time,
                    "currency": event.get("currency", ""),
                    "impact": event.get("impact", "").capitalize(),
                    "title": event.get("name", ""),
                })
        except (ValueError, KeyError):
            pass

    return result
