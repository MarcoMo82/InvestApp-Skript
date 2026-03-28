"""
Erweiterte Tests für RiskAgent – vollständige Abdeckung der Sicherheits-Features.

Abdeckung:
- has_opposing_position(): Long vs Short, gleiche/verschiedene Symbole, leere Liste
- max_lot Hard-Cap: genau an Grenze, darüber, darunter
- Max-Open-Positions: 0, 1, 2, 3 (Limit), 4 (über Limit)
- Gegenläufige Positionen via analyze()
"""

import pytest
import numpy as np
import pandas as pd

from agents.risk_agent import RiskAgent


def _make_config(
    max_open_positions: int = 3,
    max_lot: float = 1.0,
    min_crv: float = 2.0,
    risk_per_trade: float = 0.01,
    atr_sl_multiplier: float = 2.0,
    max_exposure_pct: float = 0.03,
):
    """Erstellt ein einfaches Config-Objekt."""
    return type("Config", (), {
        "max_open_positions": max_open_positions,
        "max_lot": max_lot,
        "min_crv": min_crv,
        "risk_per_trade": risk_per_trade,
        "atr_sl_multiplier": atr_sl_multiplier,
        "max_exposure_pct": max_exposure_pct,
    })()


def _make_open_order(
    symbol: str = "EURUSD",
    direction: str = "long",
    status: str = "open",
) -> dict:
    return {"symbol": symbol, "direction": direction, "status": status}


# ── Tests: has_opposing_position ─────────────────────────────────────────────

class TestHasOpposingPosition:
    """Testet has_opposing_position() als statische Methode."""

    def test_long_vs_short_same_symbol_returns_true(self):
        """Neues Long, offenes Short auf gleichem Symbol → True."""
        open_orders = [_make_open_order("EURUSD", "short", "open")]
        assert RiskAgent.has_opposing_position("EURUSD", "long", open_orders) is True

    def test_short_vs_long_same_symbol_returns_true(self):
        """Neues Short, offenes Long auf gleichem Symbol → True."""
        open_orders = [_make_open_order("EURUSD", "long", "open")]
        assert RiskAgent.has_opposing_position("EURUSD", "short", open_orders) is True

    def test_same_direction_returns_false(self):
        """Gleiche Richtung auf gleichem Symbol → False."""
        open_orders = [_make_open_order("EURUSD", "long", "open")]
        assert RiskAgent.has_opposing_position("EURUSD", "long", open_orders) is False

    def test_different_symbol_returns_false(self):
        """Gegenläufig auf ANDEREM Symbol → False."""
        open_orders = [_make_open_order("GBPUSD", "short", "open")]
        assert RiskAgent.has_opposing_position("EURUSD", "long", open_orders) is False

    def test_empty_list_returns_false(self):
        """Leere Order-Liste → False."""
        assert RiskAgent.has_opposing_position("EURUSD", "long", []) is False

    def test_closed_order_ignored(self):
        """Geschlossene Order (status='closed') wird ignoriert."""
        open_orders = [_make_open_order("EURUSD", "short", "closed")]
        assert RiskAgent.has_opposing_position("EURUSD", "long", open_orders) is False

    def test_pending_order_blocks(self):
        """Pending Order (status='pending') blockiert gegenläufigen Trade."""
        open_orders = [_make_open_order("EURUSD", "short", "pending")]
        assert RiskAgent.has_opposing_position("EURUSD", "long", open_orders) is True

    def test_multiple_orders_different_symbols(self):
        """Mehrere Orders auf verschiedenen Symbolen – nur eigenes Symbol zählt."""
        open_orders = [
            _make_open_order("GBPUSD", "short", "open"),
            _make_open_order("USDJPY", "short", "open"),
            _make_open_order("EURUSD", "long", "open"),  # gleiche Richtung
        ]
        assert RiskAgent.has_opposing_position("EURUSD", "long", open_orders) is False

    def test_via_analyze_opposing_position_blocks_trade(self):
        """analyze() mit gegenläufiger Order → trade_allowed=False."""
        agent = RiskAgent()
        open_orders = [_make_open_order("EURUSD", "short", "open")]
        result = agent.analyze({
            "symbol": "EURUSD",
            "direction": "long",
            "entry_price": 1.1000,
            "atr_value": 0.0010,
            "open_orders": open_orders,
        })
        assert result["trade_allowed"] is False
        assert "Gegenläufige Position" in result["rejection_reason"]


# ── Tests: max_lot Hard-Cap ───────────────────────────────────────────────────

class TestMaxLotHardCap:
    """Testet den max_lot Hard-Cap in _calculate_lot_size()."""

    def test_lot_exactly_at_max_not_capped(self):
        """Berechnete Lot = max_lot → wird nicht weiter gekappt."""
        max_lot = 1.0
        agent = RiskAgent(max_lot=max_lot, risk_per_trade=0.01)
        # Wir rufen _calculate_lot_size direkt auf
        # risk_amount / (sl_pips * pip_value) = max_lot → z. B. 100 / (10 * 10) = 1.0
        result = agent._calculate_lot_size(risk_amount=100.0, sl_pips=10.0, pip_value=10.0)
        assert result == pytest.approx(max_lot)

    def test_lot_above_max_capped(self):
        """Berechnete Lot > max_lot → wird auf max_lot gekappt."""
        max_lot = 0.5
        agent = RiskAgent(max_lot=max_lot)
        # risk_amount / (sl_pips * pip_value) = 1000 / (10 * 10) = 10 >> 0.5
        result = agent._calculate_lot_size(risk_amount=1000.0, sl_pips=10.0, pip_value=10.0)
        assert result == pytest.approx(max_lot)

    def test_lot_below_max_not_capped(self):
        """Berechnete Lot < max_lot → wird nicht verändert."""
        max_lot = 10.0
        agent = RiskAgent(max_lot=max_lot)
        # 10 / (10 * 10) = 0.1 << 10
        result = agent._calculate_lot_size(risk_amount=10.0, sl_pips=10.0, pip_value=10.0)
        assert result == pytest.approx(0.1)
        assert result < max_lot

    def test_max_lot_from_config_respected(self):
        """max_lot aus config wird gegenüber Konstruktor-Default priorisiert."""
        cfg = _make_config(max_lot=0.2)
        agent = RiskAgent(max_lot=10.0, config=cfg)  # config überschreibt
        assert agent.max_lot == pytest.approx(0.2)
        result = agent._calculate_lot_size(risk_amount=1000.0, sl_pips=10.0, pip_value=10.0)
        assert result == pytest.approx(0.2)

    def test_min_lot_floor_respected(self):
        """Berechnete Lot < min_lot → auf min_lot aufgerundet."""
        agent = RiskAgent(min_lot=0.01, max_lot=10.0)
        # 0.001 / (10 * 10) = 0.00001 << min_lot
        result = agent._calculate_lot_size(risk_amount=0.001, sl_pips=10.0, pip_value=10.0)
        assert result >= agent.min_lot

    def test_zero_sl_pips_returns_min_lot(self):
        """sl_pips=0 → gibt min_lot zurück (Division durch Null verhindert)."""
        agent = RiskAgent(min_lot=0.01)
        result = agent._calculate_lot_size(risk_amount=100.0, sl_pips=0.0, pip_value=10.0)
        assert result == agent.min_lot

    def test_zero_pip_value_returns_min_lot(self):
        """pip_value=0 → gibt min_lot zurück (Division durch Null verhindert)."""
        agent = RiskAgent(min_lot=0.01)
        result = agent._calculate_lot_size(risk_amount=100.0, sl_pips=10.0, pip_value=0.0)
        assert result == agent.min_lot


# ── Tests: Max Open Positions ─────────────────────────────────────────────────

class TestMaxOpenPositionsExtended:
    """Erweiterte Tests für P1.1: Max. offene Positionen."""

    def test_zero_open_positions_allowed(self):
        """open_positions=0 → nicht aus diesem Grund blockiert."""
        cfg = _make_config(max_open_positions=3)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 0,
        })
        if not result["trade_allowed"]:
            assert "Max. offene Positionen" not in result.get("rejection_reason", "")

    def test_one_open_position_allowed(self):
        """open_positions=1, max=3 → nicht aus diesem Grund blockiert."""
        cfg = _make_config(max_open_positions=3)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 1,
        })
        if not result["trade_allowed"]:
            assert "Max. offene Positionen" not in result.get("rejection_reason", "")

    def test_two_open_positions_allowed(self):
        """open_positions=2, max=3 → nicht aus diesem Grund blockiert."""
        cfg = _make_config(max_open_positions=3)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 2,
        })
        if not result["trade_allowed"]:
            assert "Max. offene Positionen" not in result.get("rejection_reason", "")

    def test_three_open_positions_at_limit_blocked(self):
        """open_positions=3, max=3 → trade_allowed=False."""
        cfg = _make_config(max_open_positions=3)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 3,
        })
        assert result["trade_allowed"] is False
        assert "Max. offene Positionen" in result["rejection_reason"]

    def test_four_open_positions_over_limit_blocked(self):
        """open_positions=4, max=3 → trade_allowed=False."""
        cfg = _make_config(max_open_positions=3)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 4,
        })
        assert result["trade_allowed"] is False

    def test_no_config_open_positions_not_checked(self):
        """Ohne Config → Max-Position-Check wird nicht ausgeführt."""
        agent = RiskAgent()  # kein config
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 100,  # viele Positionen
        })
        # Ohne config kein Position-Check → darf nicht aus diesem Grund blockiert werden
        if not result["trade_allowed"]:
            assert "Max. offene Positionen" not in result.get("rejection_reason", "")

    def test_max_positions_message_contains_count(self):
        """Ablehnungsgrund enthält aktuelle und maximale Positionsanzahl."""
        cfg = _make_config(max_open_positions=3)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "open_positions": 3,
        })
        assert "3/3" in result["rejection_reason"]


# ── Tests: Gesamtexposure-Limit ───────────────────────────────────────────────

class TestTotalExposureLimit:
    """Testet das Gesamtexposure-Limit (max_exposure_pct)."""

    def test_exposure_within_limit_allowed(self):
        """Exposure 2% + 1% neues Risiko = 3% = max → wird NICHT aus diesem Grund blockiert."""
        cfg = _make_config(max_exposure_pct=0.03, risk_per_trade=0.01)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "total_open_risk_pct": 0.02,
        })
        if not result["trade_allowed"]:
            assert "Gesamtexposure" not in result.get("rejection_reason", "")

    def test_exposure_over_limit_blocked(self):
        """Exposure 2.5% + 1% = 3.5% > 3% max → trade_allowed=False."""
        cfg = _make_config(max_exposure_pct=0.03, risk_per_trade=0.01)
        agent = RiskAgent(config=cfg)
        result = agent.analyze({
            "symbol": "EURUSD", "direction": "long",
            "entry_price": 1.1000, "atr_value": 0.0010,
            "total_open_risk_pct": 0.025,
        })
        assert result["trade_allowed"] is False
        assert "Gesamtexposure" in result["rejection_reason"]
