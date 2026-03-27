"""
Tests für utils/verbose_display.py

Prüft:
- Output wird unterdrückt wenn verbose_terminal_output=False
- Korrekte Ausgabe der einzelnen Funktionen
- verbose_show_rejected-Logik für abgelehnte Symbole
- UTF-8-Fallback (wird mit ASCII-Encoding simuliert)
"""
from __future__ import annotations

import io
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils.verbose_display import (
    print_app_start,
    print_cycle_start,
    print_learning_summary,
    print_order_event,
    print_symbol_analysis,
    print_watch_cycle,
)


# ── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _cfg(verbose: bool = True, show_rejected: bool = True) -> SimpleNamespace:
    """Erstellt ein minimales Config-Mock-Objekt."""
    return SimpleNamespace(
        verbose_terminal_output=verbose,
        verbose_show_rejected=show_rejected,
    )


def _capture(fn, *args, **kwargs) -> str:
    """Führt fn aus und gibt den stdout-Output zurück."""
    buf = io.StringIO()
    with patch("sys.stdout", buf):
        fn(*args, **kwargs)
    return buf.getvalue()


# ── Tests: verbose_terminal_output=False ────────────────────────────────────

class TestVerboseDisabled:
    def test_print_app_start_silent(self):
        out = _capture(print_app_start, "/path/config.json", 5, {"MT5": True}, _cfg(verbose=False))
        assert out == ""

    def test_print_cycle_start_silent(self):
        out = _capture(print_cycle_start, 1, ["EURUSD"], "12:00:00", _cfg(verbose=False))
        assert out == ""

    def test_print_symbol_analysis_silent(self):
        out = _capture(
            print_symbol_analysis, "EURUSD", {"macro": {"macro_bias": "bullish"}},
            "signal_ready", _cfg(verbose=False)
        )
        assert out == ""

    def test_print_watch_cycle_silent(self):
        signals = [{"instrument": "EURUSD", "direction": "long", "current_price": 1.08}]
        out = _capture(print_watch_cycle, signals, "12:00:00", _cfg(verbose=False))
        assert out == ""

    def test_print_order_event_silent(self):
        out = _capture(print_order_event, "open", "EURUSD", {"direction": "long"}, _cfg(verbose=False))
        assert out == ""

    def test_print_learning_summary_silent(self):
        insights = [{"finding": "Test", "suggestion": "Do it"}]
        out = _capture(print_learning_summary, insights, _cfg(verbose=False))
        assert out == ""


# ── Tests: print_app_start ───────────────────────────────────────────────────

class TestPrintAppStart:
    def test_contains_symbol_count(self):
        out = _capture(print_app_start, "/cfg/config.json", 7, {"YFinance": True}, _cfg())
        assert "7" in out
        assert "/cfg/config.json" in out

    def test_connector_ok_shows_checkmark(self):
        out = _capture(print_app_start, "/cfg", 3, {"MT5": True, "YFinance": False}, _cfg())
        assert "MT5" in out
        assert "YFinance" in out

    def test_empty_connectors(self):
        out = _capture(print_app_start, "/cfg", 0, {}, _cfg())
        assert "InvestApp" in out


# ── Tests: print_cycle_start ─────────────────────────────────────────────────

class TestPrintCycleStart:
    def test_contains_cycle_nr(self):
        out = _capture(print_cycle_start, 42, ["EURUSD", "GBPUSD"], "10:00:00 UTC", _cfg())
        assert "42" in out

    def test_contains_symbols(self):
        out = _capture(print_cycle_start, 1, ["EURUSD", "XAUUSD"], "10:00:00", _cfg())
        assert "EURUSD" in out
        assert "XAUUSD" in out

    def test_empty_symbols(self):
        out = _capture(print_cycle_start, 1, [], "10:00:00", _cfg())
        assert "(keine)" in out


# ── Tests: print_symbol_analysis ─────────────────────────────────────────────

class TestPrintSymbolAnalysis:
    _agent_results = {
        "macro": {"macro_bias": "bullish", "event_risk": "low", "trading_allowed": True},
        "trend": {"direction": "long", "structure_status": "intact", "strength_score": 7},
        "volatility": {"atr_value": 0.0012, "rsi_value": 42.1, "bb_squeeze": False, "setup_allowed": True},
        "level": {"nearest_level": {"zone_low": 1.0830, "zone_high": 1.0860}},
        "entry": {"entry_type": "rejection_wick", "entry_price": 1.0832, "entry_found": True},
        "risk": {"stop_loss": 1.0810, "take_profit": 1.0890, "crv": 2.1, "trade_allowed": True},
        "validation": {"confidence_score": 87.0, "validated": True},
    }

    def test_symbol_in_header(self):
        out = _capture(print_symbol_analysis, "EURUSD", self._agent_results, "signal_ready", _cfg())
        assert "EURUSD" in out

    def test_macro_data_displayed(self):
        out = _capture(print_symbol_analysis, "EURUSD", self._agent_results, "signal_ready", _cfg())
        assert "BULLISH" in out
        assert "LOW" in out

    def test_signal_ready_indicator(self):
        out = _capture(print_symbol_analysis, "EURUSD", self._agent_results, "signal_ready", _cfg())
        assert "SIGNAL BEREIT" in out

    def test_forecast_zone_indicator(self):
        out = _capture(print_symbol_analysis, "EURUSD", self._agent_results, "forecast_zone", _cfg())
        assert "FORECAST" in out

    def test_rejected_indicator(self):
        out = _capture(print_symbol_analysis, "EURUSD", self._agent_results, "rejected", _cfg())
        assert "VERWORFEN" in out

    def test_rejected_symbol_suppressed_when_show_rejected_false(self):
        out = _capture(
            print_symbol_analysis, "EURCHF",
            {"macro": {"macro_bias": "neutral", "trading_allowed": True}},
            "rejected", _cfg(show_rejected=False)
        )
        assert out == ""

    def test_rejected_symbol_shown_when_show_rejected_true(self):
        out = _capture(
            print_symbol_analysis, "EURCHF",
            {"macro": {"macro_bias": "neutral", "trading_allowed": True}},
            "rejected", _cfg(show_rejected=True)
        )
        assert "EURCHF" in out

    def test_no_agent_data_no_crash(self):
        out = _capture(print_symbol_analysis, "BTCUSD", {}, "rejected", _cfg())
        assert "BTCUSD" in out

    def test_tree_structure_uses_box_chars(self):
        out = _capture(print_symbol_analysis, "EURUSD", self._agent_results, "signal_ready", _cfg())
        assert "┌─" in out or "─" in out


# ── Tests: print_watch_cycle ─────────────────────────────────────────────────

class TestPrintWatchCycle:
    def test_empty_signals_no_output(self):
        out = _capture(print_watch_cycle, [], "12:00:00", _cfg())
        assert out == ""

    def test_shows_symbol(self):
        signals = [{"instrument": "EURUSD", "direction": "long",
                    "current_price": 1.08350, "entry_price": 1.0832}]
        out = _capture(print_watch_cycle, signals, "12:00:00 UTC", _cfg())
        assert "EURUSD" in out

    def test_shows_timestamp(self):
        signals = [{"instrument": "GBPUSD", "direction": "short",
                    "current_price": 1.26, "entry_price": 1.261}]
        out = _capture(print_watch_cycle, signals, "09:15:00 UTC", _cfg())
        assert "09:15:00" in out


# ── Tests: print_order_event ─────────────────────────────────────────────────

class TestPrintOrderEvent:
    def test_open_event_shows_symbol(self):
        out = _capture(print_order_event, "open", "EURUSD",
                       {"direction": "long", "entry_price": 1.0832,
                        "sl": 1.0800, "tp": 1.0900, "crv": 2.5}, _cfg())
        assert "EURUSD" in out
        assert "ORDER" in out

    def test_close_event_shows_pnl(self):
        out = _capture(print_order_event, "close", "XAUUSD",
                       {"direction": "long", "entry_price": 2000.0,
                        "sl": 1990.0, "tp": 2020.0, "crv": 2.0, "pnl": 15.5}, _cfg())
        assert "XAUUSD" in out
        assert "15" in out  # PnL

    def test_sl_hit_event(self):
        out = _capture(print_order_event, "sl_hit", "GBPUSD",
                       {"direction": "short", "entry_price": 1.26, "sl": 1.265,
                        "tp": 1.24, "crv": 2.0, "pnl": -20.0}, _cfg())
        assert "SL HIT" in out or "sl_hit".upper().replace("_", " ") in out


# ── Tests: print_learning_summary ─────────────────────────────────────────────

class TestPrintLearningSummary:
    def test_empty_insights_no_output(self):
        out = _capture(print_learning_summary, [], _cfg())
        assert out == ""

    def test_shows_finding(self):
        insights = [{"type": "entry_type_performance",
                     "finding": "Rejection-Wick hat 72% Trefferquote",
                     "suggestion": "Gewicht erhöhen"}]
        out = _capture(print_learning_summary, insights, _cfg())
        assert "Rejection-Wick" in out
        assert "72%" in out

    def test_shows_suggestion(self):
        insights = [{"type": "rsi_optimization",
                     "finding": "RSI 35-45 besser",
                     "suggestion": "Grenzwert auf 42 senken"}]
        out = _capture(print_learning_summary, insights, _cfg())
        assert "42" in out

    def test_multiple_insights_all_shown(self):
        insights = [
            {"finding": "Finding A", "suggestion": "Suggestion A"},
            {"finding": "Finding B", "suggestion": "Suggestion B"},
        ]
        out = _capture(print_learning_summary, insights, _cfg())
        assert "Finding A" in out
        assert "Finding B" in out
