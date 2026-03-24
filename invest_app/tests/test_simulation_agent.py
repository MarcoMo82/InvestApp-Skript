"""Tests für den SimulationAgent."""

import json
import os
import sys

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.simulation_agent import SimulationAgent


REQUIRED_SIGNAL_FIELDS = [
    "id", "timestamp", "instrument", "direction", "entry_price",
    "stop_loss", "take_profit", "lot_size", "crv", "confidence_score",
    "status", "is_simulation", "entry_type", "agent_scores",
]


def _make_config(enabled: bool = True, trigger: int = 3) -> MagicMock:
    cfg = MagicMock()
    cfg.simulation_mode_enabled = enabled
    cfg.simulation_trigger_after_watch_cycles = trigger
    cfg.simulation_symbol = "EURUSD"
    cfg.simulation_direction = "long"
    cfg.simulation_lot_size = 0.01
    return cfg


def _make_connector(price: float = 1.08450) -> MagicMock:
    connector = MagicMock()
    connector.get_current_price.return_value = {"bid": price - 0.0001, "ask": price + 0.0001, "last": price}
    connector.place_market_order.return_value = 12345678
    return connector


class TestTriggerAfterNCycles:
    def test_trigger_after_n_cycles(self):
        """Nach genau N Zyklen wird True zurückgegeben."""
        agent = SimulationAgent(_make_config(trigger=3), _make_connector())
        assert agent.on_watch_cycle() is False  # Zyklus 1
        assert agent.on_watch_cycle() is False  # Zyklus 2
        assert agent.on_watch_cycle() is True   # Zyklus 3

    def test_trigger_at_exactly_n(self):
        """Trigger genau beim N-ten Zyklus, nicht vorher."""
        agent = SimulationAgent(_make_config(trigger=1), _make_connector())
        assert agent.on_watch_cycle() is True   # Zyklus 1

    def test_no_trigger_when_disabled(self):
        """Kein Trigger wenn simulation_mode_enabled=False."""
        agent = SimulationAgent(_make_config(enabled=False, trigger=1), _make_connector())
        assert agent.on_watch_cycle() is False
        assert agent.on_watch_cycle() is False

    def test_no_double_trigger_after_mark_executed(self):
        """Kein zweiter Trigger nach mark_executed()."""
        agent = SimulationAgent(_make_config(trigger=2), _make_connector())
        agent.on_watch_cycle()         # Zyklus 1
        triggered = agent.on_watch_cycle()  # Zyklus 2 → True
        assert triggered is True
        agent.mark_executed()
        assert agent.on_watch_cycle() is False  # Zyklus 3 → False (bereits executed)
        assert agent.on_watch_cycle() is False  # Zyklus 4 → False

    def test_cycle_count_increments_only_when_enabled(self):
        """Zykluszähler wird nur inkrementiert wenn Modus aktiviert ist."""
        agent = SimulationAgent(_make_config(enabled=False, trigger=3), _make_connector())
        agent.on_watch_cycle()
        agent.on_watch_cycle()
        agent.on_watch_cycle()
        assert agent.watch_cycle_count == 0


class TestSignalStructure:
    def test_signal_has_all_required_fields(self):
        """Test-Signal enthält alle Pflichtfelder."""
        agent = SimulationAgent(_make_config(), _make_connector())
        signal = agent.generate_test_signal()
        for field in REQUIRED_SIGNAL_FIELDS:
            assert field in signal, f"Pflichtfeld fehlt: {field}"

    def test_signal_is_simulation_flag(self):
        """is_simulation ist True."""
        agent = SimulationAgent(_make_config(), _make_connector())
        signal = agent.generate_test_signal()
        assert signal["is_simulation"] is True

    def test_signal_confidence_score(self):
        """confidence_score >= 80."""
        agent = SimulationAgent(_make_config(), _make_connector())
        signal = agent.generate_test_signal()
        assert signal["confidence_score"] >= 80.0

    def test_signal_crv(self):
        """CRV ist 2.0."""
        agent = SimulationAgent(_make_config(), _make_connector())
        signal = agent.generate_test_signal()
        assert signal["crv"] == 2.0

    def test_signal_entry_type_market(self):
        """entry_type ist 'market' (damit Watch-Agent sofort ausführt)."""
        agent = SimulationAgent(_make_config(), _make_connector())
        signal = agent.generate_test_signal()
        assert signal["entry_type"] == "market"

    def test_signal_lot_size_from_config(self):
        """lot_size stammt aus config.simulation_lot_size."""
        cfg = _make_config()
        cfg.simulation_lot_size = 0.05
        agent = SimulationAgent(cfg, _make_connector())
        signal = agent.generate_test_signal()
        assert signal["lot_size"] == 0.05

    def test_signal_long_sl_below_entry(self):
        """Long-Signal: SL liegt unter entry_price."""
        agent = SimulationAgent(_make_config(), _make_connector(price=1.08450))
        signal = agent.generate_test_signal()
        assert signal["stop_loss"] < signal["entry_price"]

    def test_signal_long_tp_above_entry(self):
        """Long-Signal: TP liegt über entry_price."""
        agent = SimulationAgent(_make_config(), _make_connector(price=1.08450))
        signal = agent.generate_test_signal()
        assert signal["take_profit"] > signal["entry_price"]

    def test_signal_short_sl_above_entry(self):
        """Short-Signal: SL liegt über entry_price."""
        cfg = _make_config()
        cfg.simulation_direction = "short"
        agent = SimulationAgent(cfg, _make_connector(price=1.08450))
        signal = agent.generate_test_signal()
        assert signal["stop_loss"] > signal["entry_price"]

    def test_signal_id_starts_with_sim(self):
        """Signal-ID beginnt mit 'SIM-'."""
        agent = SimulationAgent(_make_config(), _make_connector())
        signal = agent.generate_test_signal()
        assert signal["id"].startswith("SIM-")

    def test_signal_price_fallback_when_connector_fails(self):
        """Bei Connector-Fehler wird Fallback-Preis 1.0 verwendet."""
        connector = MagicMock()
        connector.get_current_price.side_effect = RuntimeError("Verbindung unterbrochen")
        agent = SimulationAgent(_make_config(), connector)
        signal = agent.generate_test_signal()
        assert signal["entry_price"] == 1.0


class TestMarkExecuted:
    def test_mark_executed_sets_flag(self):
        """mark_executed() setzt test_executed auf True."""
        agent = SimulationAgent(_make_config(), _make_connector())
        assert agent.test_executed is False
        agent.mark_executed()
        assert agent.test_executed is True

    def test_mark_executed_writes_result_file(self, tmp_path, monkeypatch):
        """Output/simulation_result.json wird korrekt geschrieben."""
        monkeypatch.chdir(tmp_path)
        agent = SimulationAgent(_make_config(), _make_connector())
        agent.mark_executed()
        result_file = tmp_path / "Output" / "simulation_result.json"
        assert result_file.exists()
        data = json.loads(result_file.read_text())
        assert data["success"] is True
        assert "executed_at" in data
        assert "message" in data

    def test_mark_executed_file_write_error_does_not_raise(self, monkeypatch):
        """Dateischreib-Fehler wird geloggt, kein Exception nach außen."""
        import pathlib

        def broken_write(self, text):
            raise OSError("Disk full")

        monkeypatch.setattr(pathlib.Path, "write_text", broken_write)
        agent = SimulationAgent(_make_config(), _make_connector())
        agent.mark_executed()  # darf nicht werfen
        assert agent.test_executed is True
