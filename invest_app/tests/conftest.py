"""
Gemeinsame Fixtures für alle pytest-Tests.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

# Projektroot in sys.path aufnehmen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Env-Variablen für Tests setzen (kein echtes .env nötig)
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("MT5_LOGIN", "12345")
os.environ.setdefault("MT5_PASSWORD", "test")
os.environ.setdefault("MT5_SERVER", "Demo")
os.environ.setdefault("TRADING_MODE", "demo")
os.environ.setdefault("RISK_PER_TRADE", "0.01")
os.environ.setdefault("MAX_DAILY_LOSS", "0.03")


@pytest.fixture
def config():
    from config import Config
    return Config()


@pytest.fixture
def sample_ohlcv():
    """Synthetische OHLCV-Daten mit klarem Aufwärtstrend (200 Bars)."""
    np.random.seed(42)
    n = 200
    base = 100.0
    prices = [base]
    for _ in range(1, n):
        change = np.random.normal(0.05, 0.5)
        prices.append(max(prices[-1] + change, 1.0))

    df = pd.DataFrame(
        {
            "open": [p * np.random.uniform(0.998, 1.0) for p in prices],
            "high": [p * np.random.uniform(1.001, 1.01) for p in prices],
            "low": [p * np.random.uniform(0.99, 0.999) for p in prices],
            "close": prices,
            "volume": np.random.randint(1000, 10000, n),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="15min"),
    )
    return df


@pytest.fixture
def sample_ohlcv_downtrend():
    """Synthetische OHLCV-Daten mit klarem Abwärtstrend (200 Bars)."""
    np.random.seed(99)
    n = 200
    base = 150.0
    prices = [base]
    for _ in range(1, n):
        change = np.random.normal(-0.05, 0.5)
        prices.append(max(prices[-1] + change, 1.0))

    df = pd.DataFrame(
        {
            "open": [p * np.random.uniform(0.998, 1.0) for p in prices],
            "high": [p * np.random.uniform(1.001, 1.01) for p in prices],
            "low": [p * np.random.uniform(0.99, 0.999) for p in prices],
            "close": prices,
            "volume": np.random.randint(1000, 10000, n),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="15min"),
    )
    return df


@pytest.fixture
def mock_yfinance_connector(sample_ohlcv):
    connector = MagicMock()
    connector.get_ohlcv.return_value = sample_ohlcv
    connector.get_current_price.return_value = {
        "bid": 100.5,
        "ask": 100.6,
        "last": 100.55,
    }
    connector.is_available.return_value = True
    connector.get_account_balance.return_value = 10000.0
    return connector


@pytest.fixture
def mock_claude_client():
    client = MagicMock()
    client.analyze.return_value = (
        '{"macro_bias": "bullish", "event_risk": "low",'
        ' "trading_allowed": true, "key_themes": ["Fed pause"],'
        ' "reasoning": "Stable macro"}'
    )
    return client


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_daily_pnl.return_value = 0.0
    db.save_signal.return_value = True
    db.save_trade.return_value = True
    db.log_agent.return_value = True
    return db
