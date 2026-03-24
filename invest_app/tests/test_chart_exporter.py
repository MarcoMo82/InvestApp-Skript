"""
Tests für ChartExporter – JSON-Export und Konfiguration.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.chart_exporter import ChartExporter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Temporärer Pfad für die Ausgabedatei."""
    return tmp_path / "mt5_zones.json"


@pytest.fixture
def config_mock(tmp_output: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.mt5_zones_file = str(tmp_output)
    cfg.mt5_zones_export_enabled = True
    cfg.chart_entry_tolerance_pct = 0.05
    return cfg


@pytest.fixture
def agent_results() -> dict:
    return {
        "entry": {
            "entry_price": 1.08450,
            "direction": "long",
            "entry_type": "pullback",
            "entry_found": True,
        },
        "risk": {
            "stop_loss": 1.07800,
            "take_profit": 1.09400,
        },
        "trend": {
            "ema_values": {
                "ema_9": 1.08400,
                "ema_21": 1.08420,
                "ema_50": 1.08300,
                "ema_200": 1.08000,
            },
        },
        "level": {
            "all_levels": [
                {"price": 1.08200, "type": "support", "strength": 3},
                {"price": 1.09500, "type": "resistance", "strength": 2},
            ],
            "order_blocks": [
                {"high": 1.08600, "low": 1.08400, "direction": "bullish", "consumed": False}
            ],
            "psychological_levels": [1.08000, 1.09000, 1.10000],
        },
    }


# ---------------------------------------------------------------------------
# Tests: JSON-Datei wird korrekt geschrieben
# ---------------------------------------------------------------------------

class TestChartExporterWrite:

    def test_json_file_created(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results)
        exporter.save()

        assert tmp_output.exists(), "JSON-Datei wurde nicht erstellt"

    def test_json_structure_valid(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results)
        exporter.save()

        data = json.loads(tmp_output.read_text())
        assert "generated_at" in data
        assert "symbols" in data
        assert "EURUSD" in data["symbols"]

    def test_fields_complete(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results)
        exporter.save()

        sym = json.loads(tmp_output.read_text())["symbols"]["EURUSD"]

        assert "entry_zone" in sym
        assert sym["entry_zone"]["price"] == pytest.approx(1.08450)
        assert sym["entry_zone"]["direction"] == "long"
        assert sym["entry_zone"]["tolerance_pct"] == pytest.approx(0.05)
        assert sym["stop_loss"] == pytest.approx(1.07800)
        assert sym["take_profit"] == pytest.approx(1.09400)
        assert sym["ema21"] == pytest.approx(1.08420)
        assert len(sym["key_levels"]) == 2
        assert len(sym["order_blocks"]) == 1
        assert len(sym["psychological_levels"]) == 3

    def test_multiple_symbols(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results)
        exporter.export_zones("GBPUSD", agent_results)
        exporter.save()

        data = json.loads(tmp_output.read_text())
        assert "EURUSD" in data["symbols"]
        assert "GBPUSD" in data["symbols"]

    def test_key_level_fields(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results)
        exporter.save()

        sym = json.loads(tmp_output.read_text())["symbols"]["EURUSD"]
        support = next(kl for kl in sym["key_levels"] if kl["type"] == "support")
        assert support["price"] == pytest.approx(1.08200)
        assert support["strength"] == 3

    def test_signal_active_flag_without_signal(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results, signal=None)
        exporter.save()

        sym = json.loads(tmp_output.read_text())["symbols"]["EURUSD"]
        assert sym["signal_active"] is False

    def test_signal_active_flag_with_signal(self, config_mock, agent_results, tmp_output):
        mock_signal = MagicMock()
        mock_signal.entry_price = 1.0845
        mock_signal.stop_loss = 1.078
        mock_signal.take_profit = 1.094
        mock_signal.direction.value = "long"

        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results, signal=mock_signal)
        exporter.save()

        sym = json.loads(tmp_output.read_text())["symbols"]["EURUSD"]
        assert sym["signal_active"] is True


# ---------------------------------------------------------------------------
# Tests: clear_symbol
# ---------------------------------------------------------------------------

class TestClearSymbol:

    def test_clear_removes_symbol(self, config_mock, agent_results, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", agent_results)
        exporter.export_zones("GBPUSD", agent_results)
        exporter.clear_symbol("EURUSD")
        exporter.save()

        data = json.loads(tmp_output.read_text())
        assert "EURUSD" not in data["symbols"]
        assert "GBPUSD" in data["symbols"]

    def test_clear_nonexistent_symbol_no_error(self, config_mock):
        exporter = ChartExporter(config_mock)
        # Kein Fehler bei nicht vorhandenem Symbol
        exporter.clear_symbol("XYZABC")


# ---------------------------------------------------------------------------
# Tests: Export deaktiviert
# ---------------------------------------------------------------------------

class TestExportDisabled:

    def test_no_file_when_disabled(self, tmp_output):
        cfg = MagicMock()
        cfg.mt5_zones_export_enabled = False
        cfg.mt5_zones_file = str(tmp_output)

        exporter = ChartExporter(cfg)
        exporter.export_zones("EURUSD", {"entry": {}, "risk": {}, "trend": {}, "level": {}})
        exporter.save()

        assert not tmp_output.exists(), "Datei darf nicht erstellt werden wenn Export deaktiviert"

    def test_export_zones_skipped_when_disabled(self, tmp_output):
        cfg = MagicMock()
        cfg.mt5_zones_export_enabled = False
        cfg.mt5_zones_file = str(tmp_output)

        exporter = ChartExporter(cfg)
        exporter.export_zones("EURUSD", {"entry": {"entry_price": 1.08}, "risk": {}, "trend": {}, "level": {}})
        # _data bleibt leer da Export deaktiviert
        assert exporter._data == {}


# ---------------------------------------------------------------------------
# Tests: Robustheit bei fehlenden Agent-Daten
# ---------------------------------------------------------------------------

class TestRobustness:

    def test_empty_agent_results(self, config_mock, tmp_output):
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", {})
        exporter.save()

        data = json.loads(tmp_output.read_text())
        sym = data["symbols"]["EURUSD"]
        assert sym["entry_zone"] is None
        assert sym["stop_loss"] == pytest.approx(0.0)
        assert sym["key_levels"] == []
        assert sym["order_blocks"] == []
        assert sym["psychological_levels"] == []

    def test_missing_ema_values(self, config_mock, tmp_output):
        results = {
            "trend": {"ema_values": {}},
            "entry": {}, "risk": {}, "level": {},
        }
        exporter = ChartExporter(config_mock)
        exporter.export_zones("EURUSD", results)
        exporter.save()

        sym = json.loads(tmp_output.read_text())["symbols"]["EURUSD"]
        assert sym["ema21"] is None
