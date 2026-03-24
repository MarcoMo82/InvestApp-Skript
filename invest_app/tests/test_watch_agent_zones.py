"""
Tests für den Watch-Agent Zone-Update-Mechanismus.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from agents.watch_agent import WatchAgent
from agents.chart_exporter import ChartExporter


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _make_config(enabled: bool = True, tolerance_pct: float = 0.5):
    cfg = MagicMock()
    cfg.watch_agent_zone_update_enabled = enabled
    cfg.watch_agent_zone_update_entry_tolerance_pct = tolerance_pct
    cfg.watch_agent_zone_update_ob_consumed_threshold = 0.3
    cfg.mt5_zones_export_enabled = False  # kein Dateisystem-Zugriff in Tests
    cfg.mt5_zones_file = "Output/mt5_zones.json"
    return cfg


def _make_connector(bid: float, ohlcv: pd.DataFrame | None = None):
    connector = MagicMock()
    connector.get_tick.return_value = {"bid": bid, "ask": bid + 0.0001}
    connector.get_ohlcv.return_value = ohlcv
    return connector


def _make_chart_exporter(zones: dict) -> ChartExporter:
    """Gibt einen ChartExporter zurück dessen _data mit `zones` vorbelegt ist."""
    cfg = MagicMock()
    cfg.MT5_ZONES_EXPORT_ENABLED = False
    exporter = ChartExporter(config=cfg)
    exporter._data = zones
    return exporter


def _make_agent(bid: float, zones: dict, enabled: bool = True, tolerance: float = 0.5):
    config = _make_config(enabled=enabled, tolerance_pct=tolerance)
    connector = _make_connector(bid)
    exporter = _make_chart_exporter(zones)
    agent = WatchAgent(connector=connector, config=config, chart_exporter=exporter)
    return agent, exporter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_zone_update_marks_entry_inactive_when_far():
    """Entry bei 1.08500, aktueller Kurs 1.09200 (+0.65%) → inactive."""
    zones = {
        "EURUSD": {
            "entry_zone": {"price": 1.08500, "direction": "long", "type": "pullback"},
            "order_blocks": [],
        }
    }
    agent, exporter = _make_agent(bid=1.09200, zones=zones, tolerance=0.5)

    agent._update_zones_for_symbol("EURUSD")

    entry = exporter.get_zones("EURUSD")["entry_zone"]
    assert entry["active"] is False


def test_zone_update_marks_entry_active_when_close():
    """Entry bei 1.08500, aktueller Kurs 1.08510 (+0.01%) → active."""
    zones = {
        "EURUSD": {
            "entry_zone": {"price": 1.08500, "direction": "long", "type": "pullback"},
            "order_blocks": [],
        }
    }
    agent, exporter = _make_agent(bid=1.08510, zones=zones, tolerance=0.5)

    agent._update_zones_for_symbol("EURUSD")

    entry = exporter.get_zones("EURUSD")["entry_zone"]
    assert entry["active"] is True


def test_consumed_bullish_ob_removed():
    """Bullisher OB high=1.0850 low=1.0840, Kurs bei 1.0820 → konsumiert und entfernt."""
    ob = {"direction": "bullish", "high": 1.0850, "low": 1.0840, "consumed": False}
    zones = {
        "EURUSD": {
            "entry_zone": None,
            "order_blocks": [ob],
        }
    }
    agent, exporter = _make_agent(bid=1.0820, zones=zones)

    agent._update_zones_for_symbol("EURUSD")

    remaining_obs = exporter.get_zones("EURUSD").get("order_blocks", [ob])
    assert len(remaining_obs) == 0


def test_unconsumed_ob_kept():
    """OB nicht durchbrochen → bleibt in der Liste."""
    ob = {"direction": "bullish", "high": 1.0850, "low": 1.0840, "consumed": False}
    zones = {
        "EURUSD": {
            "entry_zone": None,
            "order_blocks": [ob],
        }
    }
    # Kurs oberhalb des OB → bullisher OB NICHT konsumiert
    agent, exporter = _make_agent(bid=1.0860, zones=zones)

    agent._update_zones_for_symbol("EURUSD")

    remaining_obs = exporter.get_zones("EURUSD").get("order_blocks", [ob])
    assert len(remaining_obs) == 1


def test_no_update_when_disabled():
    """WATCH_AGENT_ZONE_UPDATE_ENABLED=False → chart_exporter.save() nie aufgerufen."""
    zones = {
        "EURUSD": {
            "entry_zone": {"price": 1.08500, "direction": "long", "type": "pullback"},
            "order_blocks": [],
        }
    }
    config = _make_config(enabled=False)
    connector = _make_connector(bid=1.09200)
    exporter = _make_chart_exporter(zones)
    exporter.save = MagicMock()

    agent = WatchAgent(connector=connector, config=config, chart_exporter=exporter)
    agent._update_zones_for_symbol("EURUSD")

    exporter.save.assert_not_called()


def test_no_crash_without_chart_exporter():
    """WatchAgent ohne chart_exporter → kein Fehler bei _update_zones_for_symbol."""
    config = _make_config()
    connector = _make_connector(bid=1.08500)
    agent = WatchAgent(connector=connector, config=config, chart_exporter=None)

    # Darf nicht werfen
    agent._update_zones_for_symbol("EURUSD")
