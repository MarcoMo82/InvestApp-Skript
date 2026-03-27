"""
Session-Utilities: Handelssitzungen und zugehörige Scoring-Logik.

UTC-Zeiten:
  Asian Session:      00:00 – 09:00 UTC
  London Session:     07:00 – 16:00 UTC
  New York Session:   13:00 – 22:00 UTC
  London/NY Overlap:  13:00 – 16:00 UTC  (höchste Liquidität)
  Off-Hours:          22:00 – 00:00 UTC
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Session-Grenzen in UTC-Stunden
_ASIAN_START = 0
_ASIAN_END = 9
_LONDON_START = 7
_LONDON_END = 16
_NY_START = 13
_NY_END = 22

SESSION_ASIAN = "asian"
SESSION_LONDON = "london"
SESSION_NEW_YORK = "new_york"
SESSION_OVERLAP = "overlap"
SESSION_OFF = "off"


def get_current_session(config: Any = None) -> str:
    """
    Gibt die aktuelle Handelssession basierend auf der UTC-Zeit zurück.

    Sessionen (UTC):
      asian    – 00:00–09:00
      london   – 07:00–16:00  (exklusive Overlap)
      overlap  – 13:00–16:00  (London + NY gleichzeitig)
      new_york – 16:00–22:00  (exklusive Overlap)
      off      – 22:00–00:00

    Config-Keys (optional):
      asian_session_start_utc, asian_session_end_utc

    Args:
        config: optionales Config-Objekt für konfigurierbare Grenzen

    Returns:
        "asian" | "london" | "overlap" | "new_york" | "off"
    """
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour + now_utc.minute / 60.0

    # Grenzen aus Config lesen (Fallback auf Module-Defaults)
    asian_start = _ASIAN_START
    asian_end = _ASIAN_END
    if config is not None:
        asian_start = getattr(config, "asian_session_start_utc", _ASIAN_START)
        asian_end = getattr(config, "asian_session_end_utc", _ASIAN_END)

    if config is not None:
        london_start = config.get("london_open_hour", _LONDON_START) if hasattr(config, "get") else getattr(config, "london_open_hour", _LONDON_START)
        london_end = config.get("london_close_hour", _LONDON_END) if hasattr(config, "get") else getattr(config, "london_close_hour", _LONDON_END)
        ny_start = config.get("ny_open_hour", _NY_START) if hasattr(config, "get") else getattr(config, "ny_open_hour", _NY_START)
        ny_end = config.get("ny_close_hour", _NY_END) if hasattr(config, "get") else getattr(config, "ny_close_hour", _NY_END)
    else:
        london_start = _LONDON_START
        london_end = _LONDON_END
        ny_start = _NY_START
        ny_end = _NY_END

    in_london = london_start <= hour < london_end
    in_ny = ny_start <= hour < ny_end
    in_asian = asian_start <= hour < asian_end

    if in_london and in_ny:
        return SESSION_OVERLAP
    if in_london:
        return SESSION_LONDON
    if in_ny:
        return SESSION_NEW_YORK
    if in_asian:
        return SESSION_ASIAN
    return SESSION_OFF


def is_trend_trading_allowed(config: Any = None) -> bool:
    """
    Gibt False zurück während der Asian Session (kein Trend-Trading).
    Range-Trading bleibt in allen Sessions erlaubt.

    Config-Key: asian_session_trend_block (bool, default True)
    """
    if config is not None:
        if not getattr(config, "asian_session_trend_block", True):
            return True  # Feature deaktiviert – immer erlaubt

    session = get_current_session(config)
    return session != SESSION_ASIAN


def get_session_bonus(symbol: str, config: Any = None) -> int:
    """
    Gibt den Confidence-Bonus basierend auf der aktuellen Session zurück.

    Bonus-Regeln:
      Overlap (13–16 UTC):       +5 Punkte (konfigurierbar: session_overlap_bonus)
      London oder NY solo:        +2 Punkte (konfigurierbar: session_solo_bonus)
      Asian / Off:                 0 Punkte

    Config-Keys:
      session_scoring_enabled (bool, default True)
      session_overlap_bonus   (int,  default 5)
      session_solo_bonus      (int,  default 2)

    Args:
        symbol: Trading-Symbol (nicht session-abhängig, für spätere Erweiterung)
        config: optionales Config-Objekt

    Returns:
        Ganzzahliger Bonus-Wert
    """
    if config is not None:
        if not getattr(config, "session_scoring_enabled", True):
            return 0

    overlap_bonus = 5
    solo_bonus = 2
    if config is not None:
        overlap_bonus = getattr(config, "session_overlap_bonus", 5)
        solo_bonus = getattr(config, "session_solo_bonus", 2)

    session = get_current_session(config)

    if session == SESSION_OVERLAP:
        return overlap_bonus
    if session in (SESSION_LONDON, SESSION_NEW_YORK):
        return solo_bonus
    return 0
