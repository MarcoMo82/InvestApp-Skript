"""
Detaillierter Programmablauf im Terminal: pro Symbol Baumstruktur durch alle Agenten.
Ergänzt terminal_display.py mit strukturierter Baumansicht für Debugging und Monitoring.

Alle Funktionen prüfen config.verbose_terminal_output – wenn False, kein Output.
print_symbol_analysis prüft zusätzlich config.verbose_show_rejected für abgelehnte Symbole.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

# UTF-8-Prüfung (analog zu terminal_display.py)
_UTF8: bool = bool(
    sys.stdout.encoding and sys.stdout.encoding.lower() in ("utf-8", "utf8", "utf_8")
)

_CHECK = "✓" if _UTF8 else "[OK]"
_CROSS = "✗" if _UTF8 else "[--]"
_ICON_SIGNAL = "🟢" if _UTF8 else "[SIGNAL]"
_ICON_FORECAST = "🟡" if _UTF8 else "[FORECAST]"
_ICON_REJECTED = "🔴" if _UTF8 else "[REJECTED]"
_ICON_ROCKET = "🚀 " if _UTF8 else ""
_ICON_WATCH = "👁 " if _UTF8 else "[WATCH] "
_ICON_LEARNING = "💡 " if _UTF8 else "[LEARNING] "

_BORDER = "═" * 60
_THIN = "─" * 50


def _get_config() -> Any:
    """Lazy-Import des Singleton-Configs, um zirkuläre Imports zu vermeiden."""
    try:
        from config import config  # type: ignore[import]
        return config
    except ImportError:
        pass
    try:
        from invest_app.config import config  # type: ignore[import]
        return config
    except ImportError:
        return None


def _verbose_enabled(config: Any = None) -> bool:
    """Gibt True zurück wenn verbose_terminal_output aktiv."""
    cfg = config if config is not None else _get_config()
    if cfg is None:
        return True
    return bool(getattr(cfg, "verbose_terminal_output", True))


def _show_rejected(config: Any = None) -> bool:
    """Gibt True zurück wenn abgelehnte Symbole angezeigt werden sollen."""
    cfg = config if config is not None else _get_config()
    if cfg is None:
        return True
    return bool(getattr(cfg, "verbose_show_rejected", True))


def print_app_start(
    config_path: str,
    symbols_loaded: int,
    connectors: dict,
    config: Any = None,
) -> None:
    """Startup-Banner mit config-Pfad, geladenen Symbolen, Verbindungsstatus.

    Args:
        config_path: Pfad zur geladenen config.json
        symbols_loaded: Anzahl geladener Symbole
        connectors: Dict {name: verbunden_bool}
        config: Config-Objekt (optional, Fallback: Singleton)
    """
    if not _verbose_enabled(config):
        return

    print(_BORDER)
    print(f"  {_ICON_ROCKET}InvestApp gestartet")
    print(f"  Config:   {config_path}")
    print(f"  Symbole:  {symbols_loaded} geladen")
    for name, status in connectors.items():
        ok = _CHECK if status else _CROSS
        print(f"  {name:<14} {ok}")
    print(_BORDER)


def print_cycle_start(
    cycle_nr: int,
    symbols: list[str],
    timestamp: str,
    config: Any = None,
) -> None:
    """Zyklus-Start: welche Symbole werden analysiert.

    Args:
        cycle_nr: Laufende Zyklus-Nummer
        symbols: Liste der zu analysierenden Symbole
        timestamp: Zeitstempel-String
        config: Config-Objekt (optional)
    """
    if not _verbose_enabled(config):
        return

    sym_str = "  ".join(symbols) if symbols else "(keine)"
    arrow = "▶ " if _UTF8 else "> "
    print(f"\n{arrow}Zyklus #{cycle_nr}  [{timestamp}]  Symbole: {sym_str}")


def print_symbol_analysis(
    symbol: str,
    agent_results: dict,
    final_status: str,
    config: Any = None,
) -> None:
    """Baumstruktur für ein Symbol durch alle Agenten.

    Beispiel-Ausgabe (freigegeben):
    ┌─ EURUSD
    ├─ Macro:      Bias=BULLISH  Event-Risiko=LOW  ✓ freigegeben
    ├─ Trend:      Richtung=LONG  Struktur=INTACT  ✓ freigegeben
    ├─ Volatility: ATR=0.00120  RSI=42.1  BB-Squeeze=nein  ✓ freigegeben
    ├─ Level:      Zone=1.0830–1.0860  Distanz=1.2 ATR  ✓ freigegeben
    ├─ Entry:      Typ=Rejection-Wick  Trigger=1.08320  ✓
    ├─ Risk:       SL=1.08100  TP=1.08900  CRV=2.1  ✓ freigegeben
    └─ Validation: Confidence=87%  → 🟢 SIGNAL BEREIT

    Bei Ablehnung:
    ┌─ EURCHF
    ├─ Macro:      Bias=NEUTRAL  ✓ freigegeben
    └─ Trend:      Richtung=NEUTRAL  Struktur=  ✗ ABGEBROCHEN

    Args:
        symbol: Symbol-Name (z.B. "EURUSD")
        agent_results: Dict mit Agenten-Ergebnissen (entspricht signal.agent_scores)
        final_status: "signal_ready" | "forecast_zone" | "rejected" | "pending"
        config: Config-Objekt (optional)
    """
    if not _verbose_enabled(config):
        return

    is_rejected = final_status in ("rejected", "aborted", "no_data", "")
    if is_rejected and not _show_rejected(config):
        return

    # Zeilen als (label, text, approved_bool) sammeln
    lines: list[tuple[str, str, bool]] = []

    # Macro
    macro = agent_results.get("macro") or {}
    if macro:
        bias = str(macro.get("macro_bias", "n/a")).upper()
        risk = str(macro.get("event_risk", "n/a")).upper()
        approved = bool(macro.get("trading_allowed", True))
        ok = _CHECK if approved else _CROSS
        suffix = "" if approved else f"  {_CROSS} ABGEBROCHEN"
        # Sonderfall: UNKNOWN Event-Risiko aber Trading freigegeben (macro_unknown_risk_blocks_trading=false)
        if risk == "UNKNOWN" and approved:
            warn = " ⚠️" if _UTF8 else " [!]"
            lines.append(("macro", f"Macro:      Bias={bias}  Event-Risiko={risk}{warn}  {ok} freigegeben (mit Vorbehalt)", approved))
        else:
            lines.append(("macro", f"Macro:      Bias={bias}  Event-Risiko={risk}  {ok} freigegeben{suffix}", approved))

        # Kalender-Quelle anzeigen
        cal_source = macro.get("calendar_source", "")
        cal_count = macro.get("calendar_event_count", 0)
        if cal_source:
            if cal_source == "UNKNOWN":
                cal_line = "Kalender:   UNKNOWN (nicht erreichbar)"
            else:
                cal_line = f"Kalender:   {cal_source}  ({cal_count} High-Impact Events)"
            lines.append(("calendar", cal_line, True))

    # Trend
    trend = agent_results.get("trend") or {}
    if trend:
        direction = str(trend.get("direction", "n/a")).upper()
        structure = str(trend.get("structure_status", "n/a")).upper()
        strength = trend.get("strength_score", 0) or 0
        approved = str(trend.get("direction", "neutral")) not in ("neutral", "sideways") and strength > 4
        ok = _CHECK if approved else _CROSS
        suffix = "" if approved else f"  {_CROSS} ABGEBROCHEN"
        reason = trend.get("rejection_reason", "")
        reason_str = f"  ({reason})" if reason and not approved else ""
        lines.append(("trend", f"Trend:      Richtung={direction}  Struktur={structure}{reason_str}  {ok} freigegeben{suffix}", approved))

    # Volatility
    vol = agent_results.get("volatility") or {}
    if vol:
        atr = float(vol.get("atr_value") or 0.0)
        rsi = float(vol.get("rsi_value") or 0.0)
        squeeze = "ja" if vol.get("bb_squeeze", False) else "nein"
        approved = bool(vol.get("setup_allowed", False))
        ok = _CHECK if approved else _CROSS
        suffix = "" if approved else f"  {_CROSS} ABGEBROCHEN"
        lines.append(("volatility", f"Volatility: ATR={atr:.5f}  RSI={rsi:.1f}  BB-Squeeze={squeeze}  {ok} freigegeben{suffix}", approved))

    # Level
    level = agent_results.get("level") or {}
    if level:
        nearest = level.get("nearest_level") or {}
        zone_low = float(nearest.get("zone_low") or nearest.get("low") or 0.0)
        zone_high = float(nearest.get("zone_high") or nearest.get("high") or 0.0)
        atr_dist = float(agent_results.get("_atr_distance") or 0.0)
        approved = bool(nearest)
        ok = _CHECK if approved else _CROSS
        if zone_low > 0 and zone_high > 0:
            zone_str = f"{zone_low:.5f}–{zone_high:.5f}"
        else:
            zone_str = "n/a"
        lines.append(("level", f"Level:      Zone={zone_str}  Distanz={atr_dist:.1f} ATR  {ok} freigegeben", approved))

    # Entry
    entry = agent_results.get("entry") or {}
    if entry:
        entry_type = entry.get("entry_type", "n/a") or "n/a"
        trigger = float(entry.get("entry_price") or 0.0)
        found = bool(entry.get("entry_found", False))
        ok = _CHECK if found else _CROSS
        lines.append(("entry", f"Entry:      Typ={entry_type}  Trigger={trigger:.5f}  {ok}", found))

    # Risk
    risk = agent_results.get("risk") or {}
    if risk:
        sl = float(risk.get("stop_loss") or 0.0)
        tp = float(risk.get("take_profit") or 0.0)
        crv = float(risk.get("crv") or 0.0)
        approved = bool(risk.get("trade_allowed", False))
        ok = _CHECK if approved else _CROSS
        suffix = "" if approved else f"  {_CROSS} ABGEBROCHEN"
        lines.append(("risk", f"Risk:       SL={sl:.5f}  TP={tp:.5f}  CRV={crv:.1f}  {ok} freigegeben{suffix}", approved))

    # Validation
    validation = agent_results.get("validation") or {}
    if validation:
        conf = float(validation.get("confidence_score") or 0.0)
        if final_status == "signal_ready":
            status_icon = f"→ {_ICON_SIGNAL} SIGNAL BEREIT"
        elif final_status == "forecast_zone":
            status_icon = f"→ {_ICON_FORECAST} FORECAST-ZONE"
        else:
            status_icon = f"→ {_ICON_REJECTED} VERWORFEN ({conf:.0f}%)"
        lines.append(("validation", f"Validation: Confidence={conf:.0f}%  {status_icon}", final_status == "signal_ready"))

    if not lines:
        # Keine Agenten-Daten: Symbol war nicht analysierbar
        print(f"┌─ {symbol}")
        print(f"└─ (keine Agenten-Daten)")
        return

    # Ausgabe als Baum
    print(f"┌─ {symbol}")
    for i, (_, line, _approved) in enumerate(lines):
        prefix = "└─" if i == len(lines) - 1 else "├─"
        print(f"{prefix} {line}")


def print_watch_cycle(
    signals: list[dict],
    timestamp: str,
    config: Any = None,
) -> None:
    """Watch-Zyklus: pro Signal aktueller Preis, Distanz zur Zone, Status.

    Args:
        signals: Liste offener Signal-Dicts
        timestamp: Zeitstempel-String
        config: Config-Objekt (optional)
    """
    if not _verbose_enabled(config):
        return

    if not signals:
        return

    print(f"\n{_ICON_WATCH}Watch-Zyklus  [{timestamp}]  Signale: {len(signals)}")
    for s in signals:
        inst = s.get("instrument", "???")
        direction = str(s.get("direction", "")).upper()
        current_price = float(s.get("current_price") or 0.0)
        entry = float(s.get("entry_price") or 0.0)
        distance = abs(current_price - entry) if current_price and entry else 0.0
        status = s.get("watch_status", "ausstehend") or "ausstehend"
        price_str = f"{current_price:.5f}" if current_price else "n/a"
        dist_str = f"{distance:.5f}"
        print(f"  {inst} {direction:<5}  Preis={price_str}  Distanz={dist_str}  Status={status}")


def print_order_event(
    event_type: str,
    symbol: str,
    details: dict,
    config: Any = None,
) -> None:
    """Order-Ereignis: ausgelöst / geschlossen / SL getroffen / TP erreicht.

    Args:
        event_type: "open" | "close" | "sl_hit" | "tp_hit"
        symbol: Symbol-Name
        details: Dict mit direction, entry_price, sl, tp, crv, pnl, ticket
        config: Config-Objekt (optional)
    """
    if not _verbose_enabled(config):
        return

    event_icons: dict[str, str] = {
        "open": "🔔" if _UTF8 else "[ORDER]",
        "close": "✅" if _UTF8 else "[CLOSE]",
        "sl_hit": "🛑" if _UTF8 else "[SL]",
        "tp_hit": "🎯" if _UTF8 else "[TP]",
    }
    icon = event_icons.get(event_type, "ℹ" if _UTF8 else "[INFO]")
    direction = str(details.get("direction", "")).upper()
    ticket = details.get("ticket") or details.get("mt5_ticket", "")
    entry = float(details.get("entry_price") or 0.0)
    sl = float(details.get("sl") or details.get("stop_loss") or 0.0)
    tp = float(details.get("tp") or details.get("take_profit") or 0.0)
    crv = float(details.get("crv") or 0.0)
    pnl = details.get("pnl")

    ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    pnl_str = f"  PnL={pnl:+.2f}" if pnl is not None else ""
    ticket_str = f"  #{ticket}" if ticket else ""
    event_label = event_type.upper().replace("_", " ")

    print(f"\n{icon} ORDER {event_label}: {symbol} {direction}{ticket_str}  [{ts}]")
    print(f"   Entry={entry:.5f}  SL={sl:.5f}  TP={tp:.5f}  CRV={crv:.1f}{pnl_str}")


def print_learning_summary(
    insights: list[dict],
    config: Any = None,
) -> None:
    """Learning Agent Zusammenfassung: erkannte Muster, Vorschläge.

    Args:
        insights: Liste von Erkenntnissen mit 'finding' und 'suggestion'
        config: Config-Objekt (optional)
    """
    if not _verbose_enabled(config):
        return

    if not insights:
        return

    print(f"\n{_ICON_LEARNING}Learning Agent – Erkenntnisse")
    print(_THIN)
    for insight in insights:
        finding = insight.get("finding", "")
        suggestion = insight.get("suggestion", "")
        if finding:
            print(f"  • {finding}")
        if suggestion:
            print(f"    → {suggestion}")
    print(_THIN)
