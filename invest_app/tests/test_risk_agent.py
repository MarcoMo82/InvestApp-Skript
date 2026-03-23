"""Tests für den RiskAgent."""
import pytest

from agents.risk_agent import RiskAgent


class TestRiskAgent:
    def test_crv_minimum_long(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=1.0, account_balance=10000
        )
        assert result["trade_allowed"] is True
        assert result["crv"] >= config.min_crv
        assert result["stop_loss"] < 100.0   # SL unter Entry bei Long
        assert result["take_profit"] > 100.0  # TP über Entry bei Long

    def test_crv_minimum_short(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="short", atr=1.0, account_balance=10000
        )
        assert result["trade_allowed"] is True
        assert result["crv"] >= config.min_crv
        assert result["stop_loss"] > 100.0   # SL über Entry bei Short
        assert result["take_profit"] < 100.0  # TP unter Entry bei Short

    def test_position_size_positive(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=1.0, account_balance=10000
        )
        assert result["lot_size"] > 0

    def test_risk_amount_one_percent(self, config):
        balance = 10000.0
        agent = RiskAgent(config=config)
        # atr=0.5 → sl_distance=1.0 < max_sl=3.0 (Aktie, entry=100) ✓
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=0.5, account_balance=balance
        )
        assert result["trade_allowed"] is True
        assert result["risk_amount"] == pytest.approx(balance * 0.01)

    def test_invalid_direction_rejected(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="sideways", atr=2.0, account_balance=10000
        )
        assert result["trade_allowed"] is False
        assert result["rejection_reason"] is not None

    def test_zero_atr_rejected(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=0.0, account_balance=10000
        )
        assert result["trade_allowed"] is False

    def test_zero_entry_rejected(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=0.0, direction="long", atr=2.0, account_balance=10000
        )
        assert result["trade_allowed"] is False

    def test_output_keys_present(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=1.0, account_balance=10000
        )
        for key in ("stop_loss", "take_profit", "crv", "lot_size",
                    "sl_pips", "trade_allowed", "rejection_reason"):
            assert key in result, f"Schlüssel '{key}' fehlt im Output"

    def test_lot_size_within_bounds(self, config):
        agent = RiskAgent(config=config)
        result = agent.calculate(
            entry_price=100.0, direction="long", atr=1.0, account_balance=10000
        )
        assert agent.min_lot <= result["lot_size"] <= agent.max_lot


class TestRiskAgentSLGrenze:
    def test_forex_sl_within_80_pips_allowed(self, config):
        """Forex (entry < 100): SL ≤ 80 Pips → Trade erlaubt."""
        agent = RiskAgent(config=config)
        # atr=0.0005 → sl_distance = 0.001 (mit sl_atr_multiplier=2) → 10 Pips ≤ 80
        result = agent.calculate(
            entry_price=1.1000, direction="long", atr=0.0005, account_balance=10000
        )
        assert result["trade_allowed"] is True

    def test_forex_sl_exceeds_80_pips_rejected(self, config):
        """Forex (entry < 100): SL > 80 Pips → Trade abgelehnt."""
        agent = RiskAgent(config=config)
        # atr=0.005 → sl_distance = 0.01 mit multiplier=2 → 100 Pips > 80
        result = agent.calculate(
            entry_price=1.1000, direction="long", atr=0.005, account_balance=10000
        )
        assert result["trade_allowed"] is False
        assert result["rejection_reason"] is not None

    def test_stock_sl_within_3pct_allowed(self, config):
        """Aktie (entry >= 100): SL ≤ 3% → Trade erlaubt."""
        agent = RiskAgent(config=config)
        # entry=200, atr=1.0 → sl_distance=2.0 → 1% < 3%
        result = agent.calculate(
            entry_price=200.0, direction="long", atr=1.0, account_balance=10000
        )
        assert result["trade_allowed"] is True

    def test_stock_sl_exceeds_3pct_rejected(self, config):
        """Aktie (entry >= 100): SL > 3% → Trade abgelehnt."""
        agent = RiskAgent(config=config)
        # entry=200, atr=5.0 → sl_distance=10 → 5% > 3%
        result = agent.calculate(
            entry_price=200.0, direction="long", atr=5.0, account_balance=10000
        )
        assert result["trade_allowed"] is False
        assert result["rejection_reason"] is not None

    def test_get_max_sl_forex(self):
        """_get_max_sl_distance für Forex gibt 0.008 zurück."""
        max_sl = RiskAgent._get_max_sl_distance(1.1000, 0.001)
        assert max_sl == pytest.approx(0.008)

    def test_get_max_sl_stock(self):
        """_get_max_sl_distance für Aktie gibt 3% des Entry zurück."""
        entry = 250.0
        max_sl = RiskAgent._get_max_sl_distance(entry, 5.0)
        assert max_sl == pytest.approx(entry * 0.03)
