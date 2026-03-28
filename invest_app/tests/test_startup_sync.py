"""
Tests für startup_sync.py – Startup-Synchronisation von MT5-Positionen.

Abdeckung:
- sync_mt5_positions_to_db(): alle Pfade (None, Liste, Datei, Fehler)
- sync_from_connector(): alle Pfade (None, kein Methode, Exception)
"""

import json
import pytest
from pathlib import Path
from typing import Optional, Set
from unittest.mock import MagicMock


from agents.startup_sync import sync_mt5_positions_to_db, sync_from_connector


# ── Hilfsklassen ──────────────────────────────────────────────────────────────

class FakeOrderDB:
    """Einfache Mock-OrderDB für Tests."""

    def __init__(self, known_tickets: Optional[Set[int]] = None):
        self._known_tickets = known_tickets or set()
        self.upserted: list[dict] = []

    def get_all_open_tickets(self) -> set[int]:
        return set(self._known_tickets)

    def upsert_open_position(self, symbol, direction, ticket, lot_size,
                              entry_price, sl, tp, profit):
        self.upserted.append({
            "symbol": symbol, "direction": direction, "ticket": ticket,
            "lot_size": lot_size, "entry_price": entry_price,
            "sl": sl, "tp": tp, "profit": profit,
        })
        self._known_tickets.add(ticket)


def _make_position(ticket: int = 123456, symbol: str = "EURUSD",
                   direction: str = "buy", volume: float = 0.1) -> dict:
    return {
        "ticket": ticket, "symbol": symbol, "type": direction,
        "volume": volume, "open_price": 1.1000,
        "sl": 1.0950, "tp": 1.1100, "profit": 0.0,
    }


# ── Tests: sync_mt5_positions_to_db ──────────────────────────────────────────

class TestSyncMt5PositionsToDB:

    def test_none_order_db_returns_zero(self):
        """order_db=None → 0, kein Fehler."""
        result = sync_mt5_positions_to_db(None, [_make_position()])
        assert result == 0

    def test_none_source_returns_zero(self):
        """positions_source=None → 0, kein Fehler."""
        db = FakeOrderDB()
        result = sync_mt5_positions_to_db(db, None)
        assert result == 0
        assert len(db.upserted) == 0

    def test_empty_list_returns_zero(self):
        """Leere Liste → 0."""
        db = FakeOrderDB()
        result = sync_mt5_positions_to_db(db, [])
        assert result == 0

    def test_list_of_positions_synced(self):
        """Liste mit 2 Positionen → 2 synchronisiert."""
        db = FakeOrderDB()
        positions = [
            _make_position(ticket=100001, symbol="EURUSD"),
            _make_position(ticket=100002, symbol="GBPUSD", direction="sell"),
        ]
        result = sync_mt5_positions_to_db(db, positions)
        assert result == 2
        assert len(db.upserted) == 2

    def test_direction_buy_normalized_to_long(self):
        """type='buy' → direction='long' in DB."""
        db = FakeOrderDB()
        sync_mt5_positions_to_db(db, [_make_position(ticket=1, direction="buy")])
        assert db.upserted[0]["direction"] == "long"

    def test_direction_sell_normalized_to_short(self):
        """type='sell' → direction='short' in DB."""
        db = FakeOrderDB()
        sync_mt5_positions_to_db(db, [_make_position(ticket=2, direction="sell")])
        assert db.upserted[0]["direction"] == "short"

    def test_direction_long_kept_as_long(self):
        """direction='long' → direction='long' in DB."""
        db = FakeOrderDB()
        pos = _make_position(ticket=3)
        pos["direction"] = "long"
        del pos["type"]
        sync_mt5_positions_to_db(db, [pos])
        assert db.upserted[0]["direction"] == "long"

    def test_already_known_ticket_skipped(self):
        """Ticket bereits in DB → übersprungen, 0 synchronisiert."""
        ticket = 999001
        db = FakeOrderDB(known_tickets={ticket})
        result = sync_mt5_positions_to_db(db, [_make_position(ticket=ticket)])
        assert result == 0
        assert len(db.upserted) == 0

    def test_mixed_known_unknown_tickets(self):
        """1 bekanntes + 1 neues Ticket → 1 synchronisiert."""
        known = 1000
        new = 1001
        db = FakeOrderDB(known_tickets={known})
        positions = [
            _make_position(ticket=known, symbol="EURUSD"),
            _make_position(ticket=new, symbol="GBPUSD"),
        ]
        result = sync_mt5_positions_to_db(db, positions)
        assert result == 1
        assert db.upserted[0]["ticket"] == new

    def test_missing_ticket_field_skipped(self):
        """Position ohne 'ticket'-Feld → übersprungen."""
        db = FakeOrderDB()
        pos = {"symbol": "EURUSD", "volume": 0.1, "open_price": 1.1000}
        result = sync_mt5_positions_to_db(db, [pos])
        assert result == 0
        assert len(db.upserted) == 0

    def test_json_file_with_list(self, tmp_path):
        """JSON-Datei mit Liste → Positionen werden geladen und synchronisiert."""
        db = FakeOrderDB()
        positions = [_make_position(ticket=200001), _make_position(ticket=200002)]
        json_file = tmp_path / "positions.json"
        json_file.write_text(json.dumps(positions), encoding="utf-8")

        result = sync_mt5_positions_to_db(db, json_file)
        assert result == 2

    def test_json_file_with_positions_key(self, tmp_path):
        """JSON-Datei mit {'positions': [...]} → wird korrekt ausgelesen."""
        db = FakeOrderDB()
        data = {"positions": [_make_position(ticket=300001)]}
        json_file = tmp_path / "positions2.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")

        result = sync_mt5_positions_to_db(db, json_file)
        assert result == 1

    def test_json_file_missing(self, tmp_path):
        """Datei existiert nicht → 0, kein Fehler."""
        db = FakeOrderDB()
        missing = tmp_path / "nonexistent.json"
        result = sync_mt5_positions_to_db(db, missing)
        assert result == 0

    def test_json_file_invalid_format(self, tmp_path):
        """JSON-Datei mit ungültigem Format (dict ohne 'positions') → 0."""
        db = FakeOrderDB()
        json_file = tmp_path / "bad.json"
        json_file.write_text(json.dumps({"unknown_key": "value"}), encoding="utf-8")
        result = sync_mt5_positions_to_db(db, json_file)
        assert result == 0

    def test_json_file_broken_json(self, tmp_path):
        """Kaputtes JSON → 0, kein Crash."""
        db = FakeOrderDB()
        json_file = tmp_path / "broken.json"
        json_file.write_text("{ invalid json }", encoding="utf-8")
        result = sync_mt5_positions_to_db(db, json_file)
        assert result == 0

    def test_invalid_source_type_raises_value_error(self):
        """Ungültiger Typ als positions_source → ValueError."""
        db = FakeOrderDB()
        with pytest.raises(ValueError):
            sync_mt5_positions_to_db(db, 42)

    def test_string_path_file_exists(self, tmp_path):
        """String-Pfad statt Path-Objekt → funktioniert korrekt."""
        db = FakeOrderDB()
        positions = [_make_position(ticket=400001)]
        json_file = tmp_path / "str_path.json"
        json_file.write_text(json.dumps(positions), encoding="utf-8")

        result = sync_mt5_positions_to_db(db, str(json_file))
        assert result == 1

    def test_upsert_exception_handled_gracefully(self):
        """Fehler in upsert_open_position → wird geloggt, sync läuft weiter."""
        db = FakeOrderDB()
        db.upsert_open_position = MagicMock(side_effect=Exception("DB-Fehler"))
        positions = [_make_position(ticket=500001), _make_position(ticket=500002)]
        # Soll nicht abstürzen; beide schlagen fehl → result = 0
        result = sync_mt5_positions_to_db(db, positions)
        assert result == 0

    def test_get_all_open_tickets_exception_returns_zero(self):
        """Fehler bei get_all_open_tickets() → 0, kein Crash."""
        db = FakeOrderDB()
        db.get_all_open_tickets = MagicMock(side_effect=Exception("DB-Fehler"))
        result = sync_mt5_positions_to_db(db, [_make_position()])
        assert result == 0

    def test_lot_size_field_aliases(self):
        """'lot_size' als Alias für 'volume' wird akzeptiert."""
        db = FakeOrderDB()
        pos = {
            "ticket": 600001, "symbol": "USDJPY", "type": "buy",
            "lot_size": 0.5, "entry_price": 150.0,
            "sl": 149.0, "tp": 151.0, "profit": 0.0,
        }
        result = sync_mt5_positions_to_db(db, [pos])
        assert result == 1
        assert db.upserted[0]["lot_size"] == 0.5

    def test_ticket_as_float_converted_to_int(self):
        """Ticket als Float-Wert → wird zu int konvertiert."""
        db = FakeOrderDB()
        pos = _make_position(ticket=700001)
        pos["ticket"] = float(pos["ticket"])  # 700001.0
        result = sync_mt5_positions_to_db(db, [pos])
        assert result == 1
        assert db.upserted[0]["ticket"] == 700001


# ── Tests: sync_from_connector ────────────────────────────────────────────────

class TestSyncFromConnector:

    def test_none_connector_returns_zero(self):
        """connector=None → 0."""
        db = FakeOrderDB()
        result = sync_from_connector(db, None)
        assert result == 0

    def test_connector_without_get_open_positions_returns_zero(self):
        """Connector ohne get_open_positions() → 0."""
        db = FakeOrderDB()
        connector = object()  # Hat keine Methode
        result = sync_from_connector(db, connector)
        assert result == 0

    def test_connector_get_open_positions_exception_returns_zero(self):
        """get_open_positions() wirft Exception → 0, kein Crash."""
        db = FakeOrderDB()
        connector = MagicMock()
        connector.get_open_positions.side_effect = RuntimeError("IPC-Fehler")
        result = sync_from_connector(db, connector)
        assert result == 0

    def test_connector_returns_positions_and_syncs(self):
        """Connector gibt 2 Positionen zurück → 2 synchronisiert."""
        db = FakeOrderDB()
        connector = MagicMock()
        connector.get_open_positions.return_value = [
            _make_position(ticket=800001),
            _make_position(ticket=800002, symbol="GBPUSD"),
        ]
        result = sync_from_connector(db, connector)
        assert result == 2

    def test_connector_returns_empty_list(self):
        """Connector gibt leere Liste zurück → 0."""
        db = FakeOrderDB()
        connector = MagicMock()
        connector.get_open_positions.return_value = []
        result = sync_from_connector(db, connector)
        assert result == 0

    def test_connector_returns_none(self):
        """Connector gibt None zurück → 0, kein Crash."""
        db = FakeOrderDB()
        connector = MagicMock()
        connector.get_open_positions.return_value = None
        # None wird als positions_source weitergegeben → sync gibt 0 zurück
        result = sync_from_connector(db, connector)
        assert result == 0
