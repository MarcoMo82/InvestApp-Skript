"""
Terminal-Ausgabe: Box-Drawing-Tabellen, Signal-Monitor, Zyklus-Banner.
Alle Werte kommen aus den echten Signal-Dicts der Agenten.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

# ── Konstanten ──────────────────────────────────────────────────────────────
_W = 63          # Gesamtbreite der Trennlinie
_SEP = "═" * _W
_THIN = "─" * _W
_IND = "  "      # 2-Zeichen Einrückung für Inhaltszeilen

# UTF-8-Prüfung für Emojis und Box-Drawing
_UTF8: bool = bool(sys.stdout.encoding and sys.stdout.encoding.lower() in ("utf-8", "utf8", "utf_8"))

# Spaltenbreite pro Zelle in der 2-Spalten-Tabelle
# Gesamtbreite Box: │ col │ col │ mit Indent = 2+1+(col_w)+1+(col_w)+1 = 63
# → col_w = (63 - 2 - 3) / 2 = 29
_COL_W = 29         # Gesamtbreite inkl. führendem Leerzeichen
_COL_INNER = 27     # Nutzbarer Inhaltsbereich pro Spalte

# Innere Breite für Watch-Box: 2 + 1 + inner + 1 = 63 → inner = 59
_WATCH_INNER = 59


# ── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _p(value: float, instrument: str = "") -> str:
    """Formatiert einen Preis je nach Instrument."""
    inst = instrument.upper()
    if any(x in inst for x in ("JPY",)):
        return f"{value:.3f}"
    if any(x in inst for x in ("XAU", "XAG", "GOLD")):
        return f"{value:.2f}"
    if value >= 1000:
        return f"{value:.2f}"
    return f"{value:.5f}"


def _direction_str(direction: Any) -> str:
    """Normalisiert Direction-Enum oder String zu 'LONG'/'SHORT'."""
    d = str(direction)
    if "." in d:
        d = d.split(".")[-1]
    return d.upper()


def _trend_arrow(trend_status: str, direction: str) -> str:
    """Gibt ▲/▼ + Stärke zurück oder Plain-Text-Fallback."""
    ts = trend_status.lower()
    if not _UTF8:
        strength = "Stark" if any(w in ts for w in ("stark", "strong", "intact")) else \
                   "Mittel" if any(w in ts for w in ("mittel", "medium", "moderate")) else "Schwach"
        return f"{'UP' if direction.lower() == 'long' else 'DN'} {strength}"
    arrow = "▲" if direction.lower() == "long" else "▼"
    strength = "Stark" if any(w in ts for w in ("stark", "strong", "intact")) else \
               "Mittel" if any(w in ts for w in ("mittel", "medium", "moderate")) else "Schwach"
    return f"{arrow} {strength}"


def _entry_zone(signal: dict) -> str:
    """Extrahiert Entry-Zone aus agent_scores, Fallback: entry_price ± ATR/2."""
    inst = signal.get("instrument", "")
    agent_scores = signal.get("agent_scores") or {}

    # Versuch 1: level.nearest_level mit zone_low/zone_high
    level = agent_scores.get("level") or {} if isinstance(agent_scores, dict) else {}
    nearest = level.get("nearest_level") or {} if isinstance(level, dict) else {}
    if isinstance(nearest, dict):
        lo = nearest.get("zone_low") or nearest.get("low")
        hi = nearest.get("zone_high") or nearest.get("high")
        if lo and hi and lo != hi:
            return f"{_p(float(lo), inst)}–{_p(float(hi), inst)}"

    # Versuch 2: entry_price ± ATR * 0.5
    entry = float(signal.get("entry_price") or 0.0)
    vol = agent_scores.get("volatility") or {} if isinstance(agent_scores, dict) else {}
    atr = float(vol.get("atr_value") or 0.0) if isinstance(vol, dict) else 0.0
    if entry > 0 and atr > 0:
        return f"{_p(entry - atr * 0.5, inst)}–{_p(entry + atr * 0.5, inst)}"

    return "n/a"


def _since(timestamp: Any) -> str:
    """Berechnet verstrichene Zeit seit timestamp als HH:MM:SS."""
    if not timestamp:
        return "?"
    try:
        if isinstance(timestamp, str):
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        else:
            ts = timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = int((datetime.now(timezone.utc) - ts).total_seconds())
        h, rem = divmod(max(0, delta), 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "?"


def _trunc(text: str, width: int) -> str:
    """Kürzt Text auf width Zeichen, linksbündig aufgefüllt."""
    return text[:width].ljust(width)


# ── Öffentliche Funktionen ───────────────────────────────────────────────────

def print_separator() -> None:
    """Gibt eine ═══-Trennlinie aus."""
    print(_SEP)


def print_cycle_banner(cycle_nr: int, symbol_count: int, timestamp: str | None = None) -> None:
    """
    Zyklus-Start-Banner.

    Args:
        cycle_nr: Laufende Zyklus-Nummer.
        symbol_count: Anzahl analysierter Symbole.
        timestamp: Zeitstempel-String (Standard: aktuelle UTC-Zeit).
    """
    ts = timestamp or datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    icon = "🔄 " if _UTF8 else ""
    print(_SEP)
    print(f"{_IND}{icon}ANALYSE-ZYKLUS #{cycle_nr}  |  {ts}  |  Symbole: {symbol_count}")
    print(_SEP)


def print_signal_table(
    signals: list[dict],
    macro_info: dict | None = None,
    session: str = "",
    secondary_signals: list[dict] | None = None,
) -> None:
    """
    Top-10-Signaltabelle im 2×5-Layout mit Box-Drawing-Zeichen.

    Args:
        signals: Approved Signale als model_dump()-Dicts, sortiert nach confidence_score.
        macro_info: Makro-Kontext (macro_bias, volatility_ok, cycle_id, session).
        session: Session-Bezeichnung (überschreibt macro_info['session']).
        secondary_signals: Nachrangige Signale (<80 %) für Fußzeile.
    """
    macro_info = macro_info or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Zyklus-Label
    cycle_id = macro_info.get("cycle_id", "")
    cycle_nr_str = ""
    if cycle_id:
        parts = cycle_id.split("_")
        nr = next((p for p in reversed(parts) if p.isdigit()), "")
        cycle_nr_str = f"  |  Zyklus #{nr}" if nr else f"  |  {cycle_id}"

    icon = "📊 " if _UTF8 else ""
    print(_SEP)
    print(f"{_IND}{icon}SIGNAL-REPORT  |  {now}{cycle_nr_str}")
    print(_SEP)

    macro_bias = str(macro_info.get("macro_bias", "N/A")).upper()
    vol_label = "OK" if macro_info.get("volatility_ok", True) else "EINGESCHRÄNKT"
    session_str = session or macro_info.get("session", "N/A")
    print(f"{_IND}Makro-Bias: {macro_bias}  |  Volatilität: {vol_label}  |  Session: {session_str}")
    print(_THIN)

    if not signals:
        print(f"{_IND}Keine Signale in diesem Zyklus")
        print(_SEP)
        return

    top10 = signals[:10]
    print(f"{_IND}TOP 10 SYMBOLE")
    print(_THIN)

    # Box-Ränder
    col_border = "─" * _COL_W
    print(f"{_IND}┌{col_border}┬{col_border}┐")

    def _cell_lines(rank: int, s: dict) -> list[str]:
        inst = s.get("instrument", "???")
        d = _direction_str(s.get("direction", ""))
        conf = float(s.get("confidence_score") or 0)
        entry = float(s.get("entry_price") or 0.0)
        sl = float(s.get("stop_loss") or 0.0)
        tp = float(s.get("take_profit") or 0.0)
        crv = s.get("crv") or 0.0
        trend_status = s.get("trend_status") or ""
        zone = _entry_zone(s)

        # Zeile 1: Rang, Symbol, Richtung, Confidence
        l1 = f"#{rank} {inst:<10} {d:<5} {conf:.0f}%"
        l2 = f"   Entry: {_p(entry, inst)}"
        l3 = f"   Zone:  {zone}"
        l4 = f"   SL: {_p(sl, inst)}  TP: {_p(tp, inst)}"
        l5 = f"   Trend: {_trend_arrow(trend_status, d)}  CRV: {crv}"
        return [l1, l2, l3, l4, l5]

    EMPTY = [""] * 5

    for row in range(0, min(10, len(top10)), 2):
        left = top10[row]
        right = top10[row + 1] if row + 1 < len(top10) else None

        if row > 0:
            print(f"{_IND}├{col_border}┼{col_border}┤")

        lines_l = _cell_lines(row + 1, left)
        lines_r = _cell_lines(row + 2, right) if right else EMPTY

        for ll, lr in zip(lines_l, lines_r):
            l_pad = _trunc(ll, _COL_INNER)
            r_pad = _trunc(lr, _COL_INNER) if right else " " * _COL_INNER
            print(f"{_IND}│ {l_pad} │ {r_pad} │")

    print(f"{_IND}└{col_border}┴{col_border}┘")

    # Nachrangige Signale
    secondary = secondary_signals or []
    if secondary:
        parts = [
            f"{s.get('instrument', '?')} {float(s.get('confidence_score') or 0):.0f}%"
            for s in secondary[:6]
        ]
        print(f"{_IND}Nachrangige Signale (< 80%): {' · '.join(parts)}")

    print(_SEP)


def print_watch_update(signals: list[dict], stats: dict | None = None) -> None:
    """
    Watch-Agent-Monitor: Status aller ausstehenden Signale.

    Args:
        signals: Pending-Signal-Dicts. Können optional 'current_price' und
                 'watch_status' enthalten (werden sonst heuristisch bestimmt).
        stats: Statistik-Dict mit 'watched_symbols', 'trades_today', 'pnl_today'.
    """
    stats = stats or {}
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    count = len(signals)

    icon = "👁  " if _UTF8 else ""
    print(_SEP)
    print(f"{_IND}{icon}WATCH-UPDATE  |  {now}  |  Offene Signale: {count}")
    print(_SEP)

    watch_border = "─" * _WATCH_INNER

    if not signals:
        print(f"{_IND}Keine ausstehenden Signale.")
    else:
        print(f"{_IND}┌{watch_border}┐")

        for idx, s in enumerate(signals):
            inst = s.get("instrument", "???")
            d = _direction_str(s.get("direction", ""))
            entry = float(s.get("entry_price") or 0.0)
            sl = float(s.get("stop_loss") or 0.0)
            tp = float(s.get("take_profit") or 0.0)
            crv = s.get("crv") or 0.0
            conf = float(s.get("confidence_score") or 0)
            current_price = float(s.get("current_price") or entry)
            zone = _entry_zone(s)
            since_str = _since(s.get("timestamp"))

            # Status ermitteln
            watch_status = s.get("watch_status", "")
            if not watch_status:
                agent_scores = s.get("agent_scores") or {}
                level = agent_scores.get("level") or {} if isinstance(agent_scores, dict) else {}
                nearest = level.get("nearest_level") or {} if isinstance(level, dict) else {}
                if isinstance(nearest, dict):
                    lo = nearest.get("zone_low") or nearest.get("low")
                    hi = nearest.get("zone_high") or nearest.get("high")
                    if lo and hi and float(lo) <= current_price <= float(hi):
                        watch_status = ("✅ In Zone" if _UTF8 else "In Zone")
                    elif lo and hi:
                        dist = abs(current_price - entry)
                        dist_str = f"{_p(dist, inst)} Pips"
                        pfx = "⏳ " if _UTF8 else ""
                        watch_status = f"{pfx}Warte auf Zone  |  Distanz: {dist_str}"
                    else:
                        watch_status = "Wird überwacht"
                else:
                    watch_status = "Wird überwacht"

            # Entry-Typ / Trigger
            agent_scores = s.get("agent_scores") or {}
            entry_info = agent_scores.get("entry") or {} if isinstance(agent_scores, dict) else {}
            entry_type = entry_info.get("entry_type", "") if isinstance(entry_info, dict) else ""
            trigger_map = {
                "rejection": "Rejection-Wick ausstehend",
                "pullback": "Pullback/EMA21 ausstehend",
                "breakout": "Breakout-Retest ausstehend",
                "market": "Market-Order bereit",
            }
            trigger = trigger_map.get(entry_type, entry_type or "Trigger ausstehend")

            if idx > 0:
                print(f"{_IND}├{watch_border}┤")

            max_w = _WATCH_INNER - 2

            l1 = f"{inst}  {d}   │ Preis: {_p(current_price, inst)}  │ Entry-Zone: {zone}"
            l2 = f"Status: {watch_status}  │ {trigger}"
            l3 = f"SL: {_p(sl, inst)}  TP: {_p(tp, inst)}  CRV: {crv}  │ Conf: {conf:.0f}%  │ Seit: {since_str}"

            print(f"{_IND}│ {_trunc(l1, max_w)} │")
            print(f"{_IND}│ {_trunc(l2, max_w)} │")
            print(f"{_IND}│ {_trunc(l3, max_w)} │")

        print(f"{_IND}└{watch_border}┘")

    watched = stats.get("watched_symbols", count)
    trades_today = stats.get("trades_today", 0)
    pnl = float(stats.get("pnl_today", 0.0))
    pnl_str = f"+{pnl:.1f}" if pnl >= 0 else f"{pnl:.1f}"
    print(f"{_IND}Überwachte Symbole: {watched}  │  Heute: {trades_today} Trades  │  PnL heute: {pnl_str} Pips")
    print(_SEP)
