"""
Integrationstests: Verdrahtung aller Komponenten in build_orchestrator() / main.py.
Kein echter MT5-Aufruf – alles gemockt.

Getestete Verdrahtungsfehler:
  1. Config liest Bool-Werte case-insensitiv
  2. ChartExporter landet im Orchestrator UND im WatchAgent (gleiche Instanz)
  3. SimulationAgent im WatchAgent wenn simulation_mode_enabled=True
  4. SimulationAgent fehlt im WatchAgent wenn simulation_mode_enabled=False
  5. ScannerAgent wird im Orchestrator registriert
  6. Scanner-Ergebnis wird als active_symbols gesetzt
  7. Scanner-Fallback auf config.all_symbols wenn scan() leer zurückgibt
  8. WatchAgent ruft simulation_agent.on_watch_cycle() auf
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Hilfsfunktion: minimalen Mock-Config erzeugen der build_orchestrator benötigt
# ---------------------------------------------------------------------------

def _make_mock_config(**kwargs) -> MagicMock:
    cfg = MagicMock()
    cfg.simulation_mode_enabled = False
    cfg.scanner_enabled = True
    cfg.output_dir = Path("/tmp/invest_app_test")
    cfg.ema_periods = [9, 21, 50, 200]
    cfg.atr_period = 14
    cfg.atr_sl_multiplier = 2.0
    cfg.atr_tp_multiplier = 4.0
    cfg.min_crv = 2.0
    cfg.risk_per_trade = 0.01
    cfg.mt5_zones_export_enabled = False
    cfg.mt5_zones_file = "/tmp/invest_app_test/mt5_zones.json"
    cfg.watch_agent_zone_update_enabled = False
    cfg.simulation_trigger_after_watch_cycles = 3
    cfg.all_symbols = ["EURUSD", "GBPUSD", "USDJPY"]
    cfg.min_confidence_score = 80.0
    cfg.max_daily_loss = 0.03
    for key, val in kwargs.items():
        setattr(cfg, key, val)
    return cfg


# ---------------------------------------------------------------------------
# Test 1: Config liest Bool-Werte case-insensitiv
# ---------------------------------------------------------------------------

class TestConfigBoolParsing:
    """Config muss 'true', 'True', 'TRUE' alle als True lesen (und entsprechend False)."""

    @pytest.mark.parametrize("field,env_var", [
        ("simulation_mode_enabled", "SIMULATION_MODE_ENABLED"),
        ("news_yahoo_enabled",       "NEWS_YAHOO_ENABLED"),
        ("scanner_enabled",          "SCANNER_ENABLED"),
    ])
    def test_true_variants(self, field, env_var):
        from config import Config
        for val in ["true", "True", "TRUE"]:
            with patch.dict(os.environ, {env_var: val}):
                cfg = Config()
                assert getattr(cfg, field) is True, (
                    f"{field}: Erwartet True für Env-Wert '{val}'"
                )

    @pytest.mark.parametrize("field,env_var", [
        ("simulation_mode_enabled", "SIMULATION_MODE_ENABLED"),
        ("news_yahoo_enabled",       "NEWS_YAHOO_ENABLED"),
        ("scanner_enabled",          "SCANNER_ENABLED"),
    ])
    def test_false_variants(self, field, env_var):
        from config import Config
        for val in ["false", "False", "FALSE"]:
            with patch.dict(os.environ, {env_var: val}):
                cfg = Config()
                assert getattr(cfg, field) is False, (
                    f"{field}: Erwartet False für Env-Wert '{val}'"
                )


# ---------------------------------------------------------------------------
# Tests 2–5: build_orchestrator() Verdrahtung
# ---------------------------------------------------------------------------

class TestBuildOrchestratorWiring:
    """build_orchestrator() muss alle Komponenten korrekt verdrahten."""

    def _call_build(self, mock_config):
        """Ruft build_orchestrator() mit gemockten Abhängigkeiten auf."""
        connector = MagicMock()
        db = MagicMock()
        db.get_daily_pnl.return_value = 0.0
        claude = MagicMock()
        news = MagicMock()

        with patch("main.config", mock_config):
            from main import build_orchestrator
            return build_orchestrator(connector, db, claude, news)

    def test_chart_exporter_in_orchestrator_and_watch_agent(self):
        """Test 2: Orchestrator und WatchAgent teilen dieselbe ChartExporter-Instanz."""
        cfg = _make_mock_config(scanner_enabled=False)
        orch = self._call_build(cfg)

        assert orch.chart_exporter is not None, "Orchestrator.chart_exporter darf nicht None sein"
        assert orch.watch_agent is not None, "Orchestrator.watch_agent darf nicht None sein"
        assert orch.watch_agent.chart_exporter is not None, (
            "WatchAgent.chart_exporter darf nicht None sein"
        )
        assert orch.chart_exporter is orch.watch_agent.chart_exporter, (
            "Orchestrator und WatchAgent müssen dieselbe ChartExporter-Instanz teilen"
        )

    def test_simulation_agent_present_when_enabled(self):
        """Test 3: WatchAgent.simulation_agent ist gesetzt wenn simulation_mode_enabled=True."""
        cfg = _make_mock_config(simulation_mode_enabled=True, scanner_enabled=False)
        orch = self._call_build(cfg)

        assert orch.watch_agent.simulation_agent is not None, (
            "WatchAgent.simulation_agent muss gesetzt sein wenn simulation_mode_enabled=True"
        )

    def test_simulation_agent_absent_when_disabled(self):
        """Test 4: WatchAgent.simulation_agent ist None wenn simulation_mode_enabled=False."""
        cfg = _make_mock_config(simulation_mode_enabled=False, scanner_enabled=False)
        orch = self._call_build(cfg)

        assert orch.watch_agent.simulation_agent is None, (
            "WatchAgent.simulation_agent muss None sein wenn simulation_mode_enabled=False"
        )

    def test_scanner_agent_registered_in_orchestrator(self):
        """Test 5: Orchestrator.scanner_agent ist gesetzt wenn scanner_enabled=True."""
        cfg = _make_mock_config(scanner_enabled=True)
        orch = self._call_build(cfg)

        assert orch.scanner_agent is not None, (
            "Orchestrator.scanner_agent muss gesetzt sein wenn scanner_enabled=True"
        )


# ---------------------------------------------------------------------------
# Tests 6–7: Orchestrator._run_scanner() Logik
# ---------------------------------------------------------------------------

class TestRunScanner:
    """_run_scanner() muss active_symbols korrekt setzen."""

    def _make_orchestrator(self, scanner_agent=None, all_symbols=None):
        from agents.orchestrator import Orchestrator

        cfg = MagicMock()
        cfg.all_symbols = all_symbols or ["EURUSD", "GBPUSD", "USDJPY"]
        cfg.min_confidence_score = 80.0
        cfg.max_daily_loss = 0.03

        return Orchestrator(
            config=cfg,
            connector=MagicMock(),
            macro_agent=MagicMock(),
            trend_agent=MagicMock(),
            volatility_agent=MagicMock(),
            level_agent=MagicMock(),
            entry_agent=MagicMock(),
            risk_agent=MagicMock(),
            validation_agent=MagicMock(),
            reporting_agent=MagicMock(),
            database=MagicMock(),
            scanner_agent=scanner_agent,
        )

    def test_scanner_result_sets_active_symbols(self):
        """Test 6: scan() → ["EURUSD", "GBPUSD"] setzt active_symbols."""
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = ["EURUSD", "GBPUSD"]

        orch = self._make_orchestrator(scanner_agent=mock_scanner)
        orch._run_scanner()

        assert orch.active_symbols == ["EURUSD", "GBPUSD"], (
            "active_symbols muss dem Scanner-Ergebnis entsprechen"
        )

    def test_scanner_fallback_when_scan_empty(self):
        """Test 7: scan() → [] → Fallback auf config.all_symbols."""
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = []

        all_syms = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF"]
        orch = self._make_orchestrator(scanner_agent=mock_scanner, all_symbols=all_syms)
        orch._run_scanner()

        assert orch.active_symbols == all_syms, (
            "Bei leerem scan()-Ergebnis muss auf config.all_symbols zurückgefallen werden"
        )
        assert len(orch.active_symbols) > 0, "Fallback darf nicht leer sein"


# ---------------------------------------------------------------------------
# Test 8: WatchAgent ruft simulation_agent.on_watch_cycle() auf
# ---------------------------------------------------------------------------

class TestWatchAgentCallsSimulation:
    """WatchAgent.run_watch_cycle() muss simulation_agent.on_watch_cycle() aufrufen."""

    def test_on_watch_cycle_called(self):
        """Test 8: simulation_agent.on_watch_cycle() wird bei run_watch_cycle() aufgerufen."""
        import pandas as pd
        from agents.watch_agent import WatchAgent

        # Gemockter Connector der leere OHLCV zurückgibt (kein Entry)
        connector = MagicMock()
        connector.get_ohlcv.return_value = pd.DataFrame()

        # SimulationAgent-Mock
        sim_agent = MagicMock()
        sim_agent.on_watch_cycle.return_value = False  # kein Test-Signal auslösen

        cfg = MagicMock()
        cfg.watch_agent_zone_update_enabled = False

        watch = WatchAgent(
            connector=connector,
            db=MagicMock(),
            config=cfg,
            simulation_agent=sim_agent,
            chart_exporter=None,
        )

        watch.run_watch_cycle()

        sim_agent.on_watch_cycle.assert_called_once(), (
            "simulation_agent.on_watch_cycle() muss bei run_watch_cycle() aufgerufen werden"
        )
