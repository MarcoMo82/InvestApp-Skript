"""
Tests für utils/cycle_logger.py

Prüft:
- Datei wird im richtigen Verzeichnis erstellt
- JSON-Format stimmt mit Spezifikation überein
- Append-Modus: bestehende Datei wird erweitert, nicht überschrieben
- cycle_log_enabled=False unterdrückt jede Dateiausgabe
- Thread-Sicherheit (Lock)
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from utils.cycle_logger import CycleLogger


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    log_dir = tmp_path / "logs" / "cycles"
    log_dir.mkdir(parents=True)
    return log_dir


@pytest.fixture
def cfg(tmp_log_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        cycle_log_enabled=True,
        cycle_log_dir=tmp_log_dir,
        _path=tmp_log_dir / "config.json",
    )


@pytest.fixture
def logger_instance(cfg: SimpleNamespace) -> CycleLogger:
    return CycleLogger(config=cfg)


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _read_log(logger: CycleLogger) -> dict:
    """Liest die aktuelle Tagesdatei als Dict."""
    assert logger._file_path is not None
    return json.loads(logger._file_path.read_text(encoding="utf-8"))


# ── Tests: Initialisierung ────────────────────────────────────────────────────

class TestCycleLoggerInit:
    def test_log_dir_created(self, cfg: SimpleNamespace, tmp_log_dir: Path):
        CycleLogger(config=cfg)
        assert tmp_log_dir.exists()

    def test_no_file_before_first_write(self, logger_instance: CycleLogger):
        # Datei erst nach erstem Schreibvorgang erstellt
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        expected = logger_instance._log_dir / f"cycle_log_{today}.json"
        assert not expected.exists()

    def test_default_dir_without_config(self, tmp_path: Path):
        """CycleLogger ohne Config nutzt Default-Verzeichnis."""
        logger = CycleLogger(config=None)
        assert logger._log_dir is not None


# ── Tests: log_cycle ─────────────────────────────────────────────────────────

class TestLogCycle:
    def test_creates_file_on_first_call(self, logger_instance: CycleLogger):
        logger_instance.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD"], [])
        assert logger_instance._file_path is not None
        assert logger_instance._file_path.exists()

    def test_json_structure(self, logger_instance: CycleLogger):
        logger_instance.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD", "GBPUSD"], [])
        data = _read_log(logger_instance)
        assert "date" in data
        assert "cycles" in data
        assert "orders" in data
        assert "trade_results" in data

    def test_cycle_entry_fields(self, logger_instance: CycleLogger):
        results = [{"symbol": "EURUSD", "zone_status": "signal_ready", "direction": "long", "agents": {}}]
        logger_instance.log_cycle(42, "2026-03-27T10:15:00Z", ["EURUSD"], results)
        data = _read_log(logger_instance)
        assert len(data["cycles"]) == 1
        cycle = data["cycles"][0]
        assert cycle["cycle_nr"] == 42
        assert cycle["timestamp"] == "2026-03-27T10:15:00Z"
        assert "EURUSD" in cycle["symbols_analyzed"]
        assert len(cycle["results"]) == 1

    def test_multiple_cycles_appended(self, logger_instance: CycleLogger):
        logger_instance.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD"], [])
        logger_instance.log_cycle(2, "2026-03-27T10:05:00Z", ["GBPUSD"], [])
        data = _read_log(logger_instance)
        assert len(data["cycles"]) == 2

    def test_result_with_agents(self, logger_instance: CycleLogger):
        results = [{
            "symbol": "EURUSD",
            "zone_status": "signal_ready",
            "direction": "long",
            "agents": {
                "macro": {"bias": "bullish", "event_risk": "low", "approved": True},
                "trend": {"direction": "long", "structure": "intact", "approved": True},
                "validation": {"confidence": 87.0, "approved": True},
            },
        }]
        logger_instance.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD"], results)
        data = _read_log(logger_instance)
        result = data["cycles"][0]["results"][0]
        assert result["agents"]["macro"]["bias"] == "bullish"
        assert result["agents"]["validation"]["confidence"] == 87.0

    def test_rejected_result_has_rejection_fields(self, logger_instance: CycleLogger):
        results = [{
            "symbol": "EURCHF",
            "zone_status": "rejected",
            "direction": "neutral",
            "rejection_agent": "trend",
            "rejection_reason": "Kein klarer Trend",
            "agents": {"macro": {"bias": "neutral", "approved": True}},
        }]
        logger_instance.log_cycle(1, "2026-03-27T10:00:00Z", ["EURCHF"], results)
        data = _read_log(logger_instance)
        result = data["cycles"][0]["results"][0]
        assert result["rejection_agent"] == "trend"
        assert "Trend" in result["rejection_reason"]


# ── Tests: log_order ─────────────────────────────────────────────────────────

class TestLogOrder:
    def test_order_stored(self, logger_instance: CycleLogger):
        logger_instance.log_order(
            event="open",
            symbol="EURUSD",
            direction="long",
            entry=1.0832,
            sl=1.0810,
            tp=1.0890,
            crv=2.1,
            confidence=87.0,
            agent_params={},
        )
        data = _read_log(logger_instance)
        assert len(data["orders"]) == 1
        order = data["orders"][0]
        assert order["event"] == "open"
        assert order["symbol"] == "EURUSD"
        assert order["direction"] == "long"
        assert abs(order["entry_price"] - 1.0832) < 1e-6
        assert abs(order["crv"] - 2.1) < 1e-6
        assert abs(order["confidence"] - 87.0) < 1e-6

    def test_multiple_order_events(self, logger_instance: CycleLogger):
        for event in ("open", "close"):
            logger_instance.log_order(
                event=event, symbol="XAUUSD", direction="long",
                entry=2000.0, sl=1990.0, tp=2020.0, crv=2.0, confidence=85.0,
                agent_params={},
            )
        data = _read_log(logger_instance)
        assert len(data["orders"]) == 2

    def test_order_has_timestamp(self, logger_instance: CycleLogger):
        logger_instance.log_order(
            event="open", symbol="GBPUSD", direction="short",
            entry=1.26, sl=1.265, tp=1.24, crv=2.5, confidence=82.0,
            agent_params={},
        )
        data = _read_log(logger_instance)
        assert "timestamp" in data["orders"][0]


# ── Tests: log_trade_result ──────────────────────────────────────────────────

class TestLogTradeResult:
    def test_result_stored(self, logger_instance: CycleLogger):
        logger_instance.log_trade_result(
            symbol="EURUSD",
            direction="long",
            pnl_pips=25.5,
            outcome="win",
            agent_params={"entry_type": "rejection_wick"},
        )
        data = _read_log(logger_instance)
        assert len(data["trade_results"]) == 1
        result = data["trade_results"][0]
        assert result["symbol"] == "EURUSD"
        assert result["outcome"] == "win"
        assert abs(result["pnl_pips"] - 25.5) < 1e-6

    def test_loss_result(self, logger_instance: CycleLogger):
        logger_instance.log_trade_result(
            symbol="GBPUSD", direction="short",
            pnl_pips=-15.0, outcome="loss", agent_params={},
        )
        data = _read_log(logger_instance)
        assert data["trade_results"][0]["outcome"] == "loss"

    def test_multiple_results(self, logger_instance: CycleLogger):
        for i in range(3):
            logger_instance.log_trade_result(
                symbol="EURUSD", direction="long",
                pnl_pips=float(i * 10), outcome="win", agent_params={},
            )
        data = _read_log(logger_instance)
        assert len(data["trade_results"]) == 3


# ── Tests: cycle_log_enabled=False ───────────────────────────────────────────

class TestCycleLoggerDisabled:
    @pytest.fixture
    def disabled_cfg(self, tmp_log_dir: Path) -> SimpleNamespace:
        return SimpleNamespace(
            cycle_log_enabled=False,
            cycle_log_dir=tmp_log_dir,
            _path=tmp_log_dir / "config.json",
        )

    def test_log_cycle_no_file(self, disabled_cfg: SimpleNamespace, tmp_log_dir: Path):
        logger = CycleLogger(config=disabled_cfg)
        logger.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD"], [])
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert not (tmp_log_dir / f"cycle_log_{today}.json").exists()

    def test_log_order_no_file(self, disabled_cfg: SimpleNamespace, tmp_log_dir: Path):
        logger = CycleLogger(config=disabled_cfg)
        logger.log_order("open", "EURUSD", "long", 1.08, 1.07, 1.10, 2.0, 85.0, {})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert not (tmp_log_dir / f"cycle_log_{today}.json").exists()

    def test_log_trade_result_no_file(self, disabled_cfg: SimpleNamespace, tmp_log_dir: Path):
        logger = CycleLogger(config=disabled_cfg)
        logger.log_trade_result("EURUSD", "long", 10.0, "win", {})
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert not (tmp_log_dir / f"cycle_log_{today}.json").exists()


# ── Tests: Append-Modus ───────────────────────────────────────────────────────

class TestAppendMode:
    def test_existing_file_is_extended(self, cfg: SimpleNamespace, tmp_log_dir: Path):
        """Zwei separate Instanzen schreiben in dieselbe Tagesdatei."""
        logger1 = CycleLogger(config=cfg)
        logger1.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD"], [])

        # Zweite Instanz liest bestehende Datei und erweitert sie
        logger2 = CycleLogger(config=cfg)
        logger2.log_cycle(2, "2026-03-27T10:05:00Z", ["GBPUSD"], [])

        data = _read_log(logger2)
        assert len(data["cycles"]) == 2

    def test_corrupted_file_resets_gracefully(self, cfg: SimpleNamespace, tmp_log_dir: Path):
        """Beschädigte JSON-Datei wird neu erstellt ohne Exception."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        bad_file = tmp_log_dir / f"cycle_log_{today}.json"
        bad_file.write_text("{ invalid json }", encoding="utf-8")

        logger = CycleLogger(config=cfg)
        logger.log_cycle(1, "2026-03-27T10:00:00Z", ["EURUSD"], [])
        data = _read_log(logger)
        assert len(data["cycles"]) == 1


# ── Tests: Thread-Sicherheit ─────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_log_cycle_no_data_loss(self, logger_instance: CycleLogger):
        """10 Threads schreiben je 1 Zyklus – alle 10 müssen in der Datei landen."""
        errors: list[Exception] = []

        def write_cycle(nr: int) -> None:
            try:
                logger_instance.log_cycle(
                    nr, f"2026-03-27T10:{nr:02d}:00Z", ["EURUSD"], []
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_cycle, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Fehler in Threads: {errors}"
        data = _read_log(logger_instance)
        assert len(data["cycles"]) == 10
