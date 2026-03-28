"""
startup_sync.py – Startup-Synchronisation von MT5-Positionen in die Order-DB.

Problem: Nach Neustart der InvestApp sind bestehende MT5-Positionen nicht in
der Order-DB → System könnte Duplikate erzeugen oder Positionen nicht überwachen.

Lösung: Beim Start alle offenen MT5-Positionen einlesen und fehlende in die DB
einfügen (Status 'open'). Bereits bekannte Positionen werden nicht verändert.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from utils.logger import get_logger

logger = get_logger(__name__)


def sync_mt5_positions_to_db(
    order_db,
    positions_source: Union[str, Path, list, None],
) -> int:
    """
    Synchronisiert offene MT5-Positionen in die Order-DB.

    Für jede Position wird geprüft ob das MT5-Ticket bereits in der DB existiert.
    Fehlende Positionen werden mit Status 'open' eingefügt.
    Vorhandene Datensätze werden nicht verändert.

    Args:
        order_db:          OrderDB-Instanz
        positions_source:  Eine der folgenden Quellen:
                           - list[dict]: Liste von Positions-Dicts (direkt vom Connector)
                           - str | Path: Pfad zu einer JSON-Datei mit Positions-Liste
                           - None:       Keine Quelle → 0 synchronisiert, kein Fehler

    Returns:
        Anzahl neu synchronisierter Positionen.

    Raises:
        ValueError: Wenn positions_source ein ungültiger Typ ist.
    """
    if order_db is None:
        logger.warning("[StartupSync] Kein order_db übergeben – Sync übersprungen")
        return 0

    # ── Positionen laden ──────────────────────────────────────────────────────
    positions: list[dict] = []

    if positions_source is None:
        logger.info("[StartupSync] Keine Positionsquelle angegeben – Sync übersprungen")
        return 0

    elif isinstance(positions_source, (str, Path)):
        path = Path(positions_source)
        if not path.exists():
            logger.warning(f"[StartupSync] Positionsdatei nicht gefunden: {path} – Sync übersprungen")
            return 0
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                positions = data
            elif isinstance(data, dict) and "positions" in data:
                positions = data["positions"]
            else:
                logger.warning(f"[StartupSync] Unbekanntes JSON-Format in {path} – Sync übersprungen")
                return 0
            logger.info(f"[StartupSync] {len(positions)} Positionen aus {path} geladen")
        except Exception as e:
            logger.error(f"[StartupSync] Fehler beim Lesen von {path}: {e}")
            return 0

    elif isinstance(positions_source, list):
        positions = positions_source
        logger.info(f"[StartupSync] {len(positions)} Positionen direkt übergeben")

    else:
        raise ValueError(f"[StartupSync] Ungültiger Typ für positions_source: {type(positions_source)}")

    if not positions:
        logger.info("[StartupSync] Keine offenen MT5-Positionen vorhanden – keine Sync nötig")
        return 0

    # ── Vorhandene Tickets aus der DB holen ───────────────────────────────────
    try:
        known_tickets: set[int] = order_db.get_all_open_tickets()
    except Exception as e:
        logger.error(f"[StartupSync] Fehler beim Lesen bekannter Tickets: {e}")
        return 0

    # ── Positionen synchronisieren ────────────────────────────────────────────
    synced = 0
    for pos in positions:
        ticket = pos.get("ticket")
        if ticket is None:
            logger.warning(f"[StartupSync] Position ohne Ticket übersprungen: {pos}")
            continue

        ticket = int(ticket)
        if ticket in known_tickets:
            logger.debug(f"[StartupSync] Ticket {ticket} bereits in DB – übersprungen")
            continue

        # Richtung normalisieren (long/buy → 'long', short/sell → 'short')
        raw_dir = pos.get("direction", pos.get("type", "buy")).lower()
        direction = "long" if raw_dir in ("long", "buy", "0") else "short"

        try:
            order_db.upsert_open_position(
                symbol=pos.get("symbol", "UNKNOWN"),
                direction=direction,
                ticket=ticket,
                lot_size=float(pos.get("volume", pos.get("lot_size", 0.0))),
                entry_price=float(pos.get("open_price", pos.get("entry_price", 0.0))),
                sl=float(pos.get("sl", 0.0)),
                tp=float(pos.get("tp", 0.0)),
                profit=float(pos.get("profit", 0.0)),
            )
            synced += 1
            logger.info(
                f"[StartupSync] Ticket {ticket} synchronisiert: "
                f"{pos.get('symbol', '?')} {direction.upper()} "
                f"| Lots={pos.get('volume', pos.get('lot_size', '?'))} "
                f"| Entry={pos.get('open_price', pos.get('entry_price', '?'))}"
            )
        except Exception as e:
            logger.error(f"[StartupSync] Fehler beim Einfügen von Ticket {ticket}: {e}")

    logger.info(
        f"[StartupSync] Abgeschlossen: {synced} neue Position(en) synchronisiert "
        f"(gesamt gefunden: {len(positions)}, bereits bekannt: {len(positions) - synced})"
    )
    return synced


def sync_from_connector(order_db, connector) -> int:
    """
    Convenience-Wrapper: Liest Positionen direkt vom MT5-Connector.

    Args:
        order_db:   OrderDB-Instanz
        connector:  Connector mit get_open_positions()-Methode (MT5Connector)

    Returns:
        Anzahl neu synchronisierter Positionen.
    """
    if connector is None:
        logger.info("[StartupSync] Kein Connector übergeben – Sync übersprungen")
        return 0

    if not hasattr(connector, "get_open_positions"):
        logger.info("[StartupSync] Connector hat keine get_open_positions()-Methode – Sync übersprungen")
        return 0

    try:
        positions = connector.get_open_positions()
    except Exception as e:
        logger.warning(f"[StartupSync] get_open_positions() Fehler: {e} – Sync übersprungen")
        return 0

    return sync_mt5_positions_to_db(order_db, positions)
