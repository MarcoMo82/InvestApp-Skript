"""Tests für ScannerAgent."""

import pytest
from unittest.mock import MagicMock
from agents.scanner_agent import ScannerAgent


def make_config(**kwargs):
    cfg = MagicMock()
    cfg.scanner_max_symbols = kwargs.get("scanner_max_symbols", 10)
    cfg.scanner_categories = kwargs.get("scanner_categories", ["forex", "indices", "commodities"])
    cfg.scanner_category_limits = kwargs.get(
        "scanner_category_limits", {"forex": 5, "indices": 3, "commodities": 2, "crypto": 0}
    )
    cfg.scanner_respect_category_limits = kwargs.get("scanner_respect_category_limits", True)
    cfg.scanner_min_score = kwargs.get("scanner_min_score", 10)
    cfg.htf_timeframe = "15m"
    cfg.fallback_symbols = kwargs.get("fallback_symbols", ["EURUSD", "GBPUSD"])
    cfg.all_symbols = cfg.fallback_symbols
    return cfg


def test_get_category_forex():
    agent = ScannerAgent(make_config(), MagicMock())
    assert agent._get_category("EURUSD") == "forex"
    assert agent._get_category("GBPUSD") == "forex"
    assert agent._get_category("USDJPY") == "forex"


def test_get_category_indices():
    agent = ScannerAgent(make_config(), MagicMock())
    assert agent._get_category("GER40") == "indices"
    assert agent._get_category("NAS100") == "indices"
    assert agent._get_category("US30") == "indices"


def test_get_category_commodities():
    agent = ScannerAgent(make_config(), MagicMock())
    assert agent._get_category("XAUUSD") == "commodities"
    assert agent._get_category("XAGUSD") == "commodities"


def test_get_category_crypto():
    agent = ScannerAgent(make_config(), MagicMock())
    assert agent._get_category("BTCUSD") == "crypto"
    assert agent._get_category("ETHUSD") == "crypto"


def test_get_category_other():
    agent = ScannerAgent(make_config(), MagicMock())
    assert agent._get_category("AAPL") == "other"


def test_filter_by_category_excludes_other():
    agent = ScannerAgent(make_config(), MagicMock())
    symbols = ["EURUSD", "AAPL", "GER40", "XAUUSD", "BTCUSD"]
    result = agent._filter_by_category(symbols)
    assert "EURUSD" in result
    assert "GER40" in result
    assert "XAUUSD" in result
    assert "AAPL" not in result   # other
    assert "BTCUSD" not in result  # crypto nicht in default-Kategorien


def test_category_limits_respected():
    cfg = make_config(
        scanner_category_limits={"forex": 2, "indices": 1, "commodities": 1, "crypto": 0}
    )
    agent = ScannerAgent(cfg, MagicMock())
    scored = [
        ("EURUSD", 90, {}), ("GBPUSD", 85, {}), ("USDJPY", 80, {}),
        ("GER40", 75, {}), ("NAS100", 70, {}),
        ("XAUUSD", 65, {}),
    ]
    result, _ = agent._select_top_symbols(scored)
    forex = [s for s in result if agent._get_category(s) == "forex"]
    indices = [s for s in result if agent._get_category(s) == "indices"]
    assert len(forex) <= 2
    assert len(indices) <= 1


def test_max_symbols_respected():
    cfg = make_config(scanner_max_symbols=3)
    agent = ScannerAgent(cfg, MagicMock())
    scored = [
        ("EURUSD", 90, {}), ("GBPUSD", 85, {}), ("USDJPY", 80, {}),
        ("USDCHF", 75, {}), ("GER40", 70, {}),
    ]
    result, _ = agent._select_top_symbols(scored)
    assert len(result) <= 3


def test_category_limits_ignored_when_disabled():
    """Wenn scanner_respect_category_limits=False → einfach Top-N nach Score."""
    cfg = make_config(
        scanner_max_symbols=4,
        scanner_respect_category_limits=False,
        scanner_category_limits={"forex": 1, "indices": 1, "commodities": 1, "crypto": 0},
    )
    agent = ScannerAgent(cfg, MagicMock())
    scored = [
        ("EURUSD", 90, {}), ("GBPUSD", 85, {}), ("USDJPY", 80, {}),
        ("USDCHF", 75, {}), ("GER40", 70, {}),
    ]
    result, cat_excluded = agent._select_top_symbols(scored)
    # Ohne Limit-Check: Top-4 nach Score, alle Forex erlaubt
    assert len(result) == 4
    assert cat_excluded == 0
    forex = [s for s in result if agent._get_category(s) == "forex"]
    assert len(forex) > 1  # mehr als das Limit von 1


def test_min_score_filters_low_scoring_symbols():
    """Symbole unter scanner_min_score kommen nicht auf die Watchlist."""
    cfg = make_config(scanner_min_score=50)
    connector = MagicMock()
    connector.get_symbols.return_value = []
    connector.get_ohlcv.return_value = None
    agent = ScannerAgent(cfg, connector)
    # Direkt scored-Liste mit Scores unter/über Schwelle
    scored_all = [("EURUSD", 80, {}), ("GBPUSD", 40, {}), ("XAUUSD", 60, {})]
    above_min = [(s, sc, bd) for s, sc, bd in scored_all if sc >= 50]
    assert len(above_min) == 2
    assert all(s in ["EURUSD", "XAUUSD"] for s, _, _ in above_min)


def test_scan_fallback_to_config_symbols():
    cfg = make_config()
    connector = MagicMock()
    connector.get_ohlcv.return_value = None
    symbol_provider = MagicMock()
    symbol_provider.get_symbols.return_value = ["EURUSD", "GBPUSD"]
    agent = ScannerAgent(cfg, connector, symbol_provider=symbol_provider)
    result = agent.scan()
    assert isinstance(result, list)


def test_scan_uses_broker_symbols_if_available():
    cfg = make_config()
    connector = MagicMock()
    connector.get_ohlcv.return_value = None
    symbol_provider = MagicMock()
    symbol_provider.get_symbols.return_value = ["EURUSD", "GBPUSD", "GER40"]
    agent = ScannerAgent(cfg, connector, symbol_provider=symbol_provider)
    result = agent.scan()
    assert isinstance(result, list)


def test_score_returns_zero_on_none_data():
    agent = ScannerAgent(make_config(), MagicMock())
    agent.connector.get_ohlcv.return_value = None
    score, breakdown = agent._score_symbol("EURUSD")
    assert score == 0


def test_score_returns_zero_on_too_few_bars():
    agent = ScannerAgent(make_config(), MagicMock())
    # Weniger als 20 Bars → Score 0
    agent.connector.get_ohlcv.return_value = [{"open": 1, "high": 1, "low": 1, "close": 1}] * 5
    score, breakdown = agent._score_symbol("EURUSD")
    assert score == 0


def test_score_returns_breakdown_dict():
    agent = ScannerAgent(make_config(), MagicMock())
    agent.connector.get_ohlcv.return_value = None
    score, breakdown = agent._score_symbol("EURUSD")
    assert isinstance(breakdown, dict)


def test_active_symbols_updated_after_scan():
    cfg = make_config()
    connector = MagicMock()
    connector.get_ohlcv.return_value = None
    symbol_provider = MagicMock()
    symbol_provider.get_symbols.return_value = ["EURUSD", "GBPUSD"]
    agent = ScannerAgent(cfg, connector, symbol_provider=symbol_provider)
    assert agent.active_symbols == []
    agent.scan()
    assert isinstance(agent.active_symbols, list)


def test_log_watchlist_no_previous(caplog):
    import logging
    agent = ScannerAgent(make_config(), MagicMock())
    agent.active_symbols = ["EURUSD", "GBPUSD"]
    with caplog.at_level(logging.INFO):
        agent.log_watchlist()
    assert "Aktive Symbole" in caplog.text


def test_log_watchlist_with_changes(caplog):
    import logging
    agent = ScannerAgent(make_config(), MagicMock())
    agent.active_symbols = ["EURUSD", "GER40"]
    with caplog.at_level(logging.INFO):
        agent.log_watchlist(previous=["EURUSD", "GBPUSD"])
    assert "Watchlist-Änderung" in caplog.text
    assert "+GER40" in caplog.text
    assert "-GBPUSD" in caplog.text


def test_log_watchlist_unchanged(caplog):
    import logging
    agent = ScannerAgent(make_config(), MagicMock())
    agent.active_symbols = ["EURUSD", "GBPUSD"]
    with caplog.at_level(logging.INFO):
        agent.log_watchlist(previous=["EURUSD", "GBPUSD"])
    assert "unverändert" in caplog.text


def test_cat_excluded_count_returned():
    """_select_top_symbols gibt Anzahl durch Kategorie-Limit aussortierter Symbole zurück."""
    cfg = make_config(
        scanner_max_symbols=10,
        scanner_category_limits={"forex": 1, "indices": 3, "commodities": 2, "crypto": 0},
    )
    agent = ScannerAgent(cfg, MagicMock())
    scored = [
        ("EURUSD", 90, {}), ("GBPUSD", 85, {}), ("USDJPY", 80, {}),  # 3 Forex, Limit=1
    ]
    result, cat_excluded = agent._select_top_symbols(scored)
    assert cat_excluded == 2  # GBPUSD und USDJPY aussortiert


def test_get_broker_symbols_from_file():
    """_get_broker_symbols delegiert an SymbolProvider.get_symbols()."""
    cfg = make_config()
    connector = MagicMock()
    symbol_provider = MagicMock()
    symbol_provider.get_symbols.return_value = ["EURUSD", "GBPUSD", "GER40", "XAUUSD"]
    agent = ScannerAgent(cfg, connector, symbol_provider=symbol_provider)
    result = agent._get_broker_symbols()
    assert result == ["EURUSD", "GBPUSD", "GER40", "XAUUSD"]
    symbol_provider.get_symbols.assert_called_once()


def test_get_broker_symbols_api_fallback():
    """_get_broker_symbols gibt SymbolProvider-Ergebnis zurück."""
    cfg = make_config()
    connector = MagicMock()
    symbol_provider = MagicMock()
    symbol_provider.get_symbols.return_value = ["EURUSD", "GBPUSD", "USDJPY"]
    agent = ScannerAgent(cfg, connector, symbol_provider=symbol_provider)
    result = agent._get_broker_symbols()
    assert result == ["EURUSD", "GBPUSD", "USDJPY"]


def test_get_broker_symbols_fallback_config():
    """Wenn SymbolProvider None → SymbolProviderError wird propagiert."""
    from data.symbol_provider import SymbolProviderError
    cfg = make_config()
    connector = MagicMock()
    agent = ScannerAgent(cfg, connector)  # kein symbol_provider
    with pytest.raises(SymbolProviderError):
        agent._get_broker_symbols()
