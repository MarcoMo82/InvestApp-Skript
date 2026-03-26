"""
Economic Calendar – holt High-Impact Events von ForexFactory.
Liefert Events im konfigurierbaren Zeitfenster für den News-Block (P1.4).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from utils.logger import get_logger

logger = get_logger(__name__)

FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_REQUEST_TIMEOUT = 5  # Sekunden


def get_upcoming_high_impact_events(
    minutes_before: int = 30,
    minutes_after: int = 30,
) -> list[dict]:
    """
    Gibt High-Impact Wirtschaftsereignisse zurück, die innerhalb des
    angegebenen Zeitfensters um jetzt liegen.

    Args:
        minutes_before: Minuten VOR dem Event, die geblockt werden
        minutes_after:  Minuten NACH dem Event, die geblockt werden

    Returns:
        Liste von Dicts:
            {"time": datetime, "currency": str, "impact": str, "title": str}
        Leere Liste wenn API nicht erreichbar (Fail-Safe: kein Block).
    """
    try:
        resp = requests.get(FF_CALENDAR_URL, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        raw_events: list[dict] = resp.json()
    except requests.RequestException as e:
        logger.warning(
            f"[EconomicCalendar] ForexFactory nicht erreichbar – kein News-Block aktiv: {e}"
        )
        return []
    except ValueError as e:
        logger.warning(f"[EconomicCalendar] JSON-Parsing fehlgeschlagen: {e}")
        return []

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=minutes_after)
    window_end = now + timedelta(minutes=minutes_before)

    events: list[dict] = []
    for raw in raw_events:
        if raw.get("impact", "").lower() != "high":
            continue

        date_str = raw.get("date", "")
        if not date_str:
            continue

        try:
            event_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            logger.debug(f"[EconomicCalendar] Unbekanntes Datum-Format: {date_str!r}")
            continue

        if window_start <= event_time <= window_end:
            events.append({
                "time": event_time,
                "currency": raw.get("country", "").upper(),
                "impact": "High",
                "title": raw.get("title", raw.get("name", "Unbekanntes Event")),
            })

    if events:
        logger.info(
            f"[EconomicCalendar] {len(events)} High-Impact Event(s) im "
            f"±{minutes_before}/{minutes_after}-Min-Fenster gefunden."
        )
    else:
        logger.debug(
            f"[EconomicCalendar] Keine High-Impact Events im "
            f"±{minutes_before}/{minutes_after}-Min-Fenster."
        )

    return events
