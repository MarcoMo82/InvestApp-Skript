"""
Tests für MT5Connector – ohne echte MT5-Installation (vollständig gemockt).
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# MT5 mocken bevor der Import von mt5_connector stattfindet
# ---------------------------------------------------------------------------

def _build_mt5_mock() -> MagicMock:
    m = MagicMock()
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.TRADE_ACTION_DEAL = 1
    m.TRADE_ACTION_SLTP = 6
    m.ORDER_TIME_GTC = 1
    m.ORDER_FILLING_IOC = 1
    m.TRADE_RETCODE_DONE = 10009
    return m


_mt5_mock = _build_mt5_mock()
sys.modules.setdefault("MetaTrader5", _mt5_mock)

# Jetzt erst importieren
from data.mt5_connector import MT5Connector  # noqa: E402


# ---------------------------------------------------------------------------
# Hilfsfunktion: minimalen Connector ohne echte MT5-Verbindung bauen
# ---------------------------------------------------------------------------

def _make_connector(config=None) -> MT5Connector:
    """Baut MT5Connector ohne __init__-Guard (MT5_AVAILABLE patch)."""
    with patch("data.mt5_connector.MT5_AVAILABLE", True):
        connector = MT5Connector.__new__(MT5Connector)
    connector.login = 0
    connector.password = ""
    connector.server = ""
    connector.path = ""
    connector.config = config
    connector._connected = False
    connector._last_ipc_log = None
    return connector


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetCommonFilesPath:
    def test_returns_configured_path_when_set(self, tmp_path):
        """Wenn mt5_common_files_path gesetzt → diesen Pfad zurückgeben."""
        cfg = SimpleNamespace(mt5_common_files_path=str(tmp_path), output_dir=str(tmp_path))
        connector = _make_connector(config=cfg)
        result = connector._get_common_files_path()
        assert result == tmp_path

    def test_fallback_path_when_config_empty(self, tmp_path, monkeypatch):
        """Wenn mt5_common_files_path leer ist und APPDATA nicht gesetzt → Output-Dir."""
        monkeypatch.delenv("APPDATA", raising=False)
        cfg = SimpleNamespace(mt5_common_files_path="", output_dir=str(tmp_path))
        connector = _make_connector(config=cfg)
        result = connector._get_common_files_path()
        assert result.exists()
        assert result == tmp_path

    def test_fallback_path_when_no_config(self, tmp_path, monkeypatch):
        """Wenn kein config übergeben wird → kein Crash, valider Pfad."""
        monkeypatch.delenv("APPDATA", raising=False)
        connector = _make_connector(config=None)
        # Config-Import mocken damit kein echter config.json nötig ist
        mock_cfg = SimpleNamespace(mt5_common_files_path="", output_dir=str(tmp_path))
        with patch("data.mt5_connector.MT5Connector._get_common_files_path",
                   return_value=tmp_path):
            result = connector._get_common_files_path()
        assert result == tmp_path

    def test_appdata_path_used_when_exists(self, tmp_path, monkeypatch):
        """Wenn APPDATA/MetaQuotes/Terminal/Common/Files existiert → diesen Pfad nutzen."""
        common_files = tmp_path / "MetaQuotes" / "Terminal" / "Common" / "Files"
        common_files.mkdir(parents=True)
        monkeypatch.setenv("APPDATA", str(tmp_path))
        cfg = SimpleNamespace(mt5_common_files_path="", output_dir=str(tmp_path / "Output"))
        connector = _make_connector(config=cfg)
        result = connector._get_common_files_path()
        assert result == common_files


class TestWriteOrderFile:
    def test_writes_json_to_correct_path(self, tmp_path):
        """write_order_file schreibt pending_order.json in den common-files-Pfad."""
        cfg = SimpleNamespace(mt5_common_files_path=str(tmp_path), output_dir=str(tmp_path))
        connector = _make_connector(config=cfg)

        signal = {
            "symbol": "EURUSD",
            "direction": "buy",
            "volume": 0.01,
            "sl": 1.0900,
            "tp": 1.1200,
        }
        result = connector.write_order_file(signal)
        assert result is True

        order_file = tmp_path / "pending_order.json"
        assert order_file.exists()

        import json
        data = json.loads(order_file.read_text())
        assert data["symbol"] == "EURUSD"
        assert data["direction"] == "buy"
        assert data["status"] == "pending"


class TestReconnect:
    def test_reconnect_on_ipc_error_get_ohlcv(self):
        """get_ohlcv: None + IPC-Fehler -10001 → _try_reconnect wird aufgerufen."""
        connector = _make_connector()
        connector._connected = True

        import numpy as np
        dummy_rates = np.array(
            [(1700000000, 1.1, 1.2, 1.0, 1.15, 100)],
            dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"),
                   ("low", "f8"), ("close", "f8"), ("tick_volume", "i8")],
        )

        call_count = {"n": 0}

        def fake_copy_rates(symbol, tf, pos, bars):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # erstes Mal schlägt fehl
            return dummy_rates  # nach Reconnect OK

        _mt5_mock.copy_rates_from_pos.side_effect = fake_copy_rates
        _mt5_mock.last_error.return_value = (-10001, "IPC send failed")

        with patch.object(connector, "_try_reconnect", return_value=True) as mock_reconnect:
            result = connector.get_ohlcv("EURUSD", "15m", 10)

        mock_reconnect.assert_called_once()
        assert not result.empty

    def test_no_reconnect_on_normal_error(self):
        """get_ohlcv: None + normaler Fehler → kein Reconnect."""
        connector = _make_connector()
        connector._connected = True

        _mt5_mock.copy_rates_from_pos.return_value = None
        _mt5_mock.copy_rates_from_pos.side_effect = None
        _mt5_mock.last_error.return_value = (-1, "Allgemeiner Fehler")

        with patch.object(connector, "_try_reconnect") as mock_reconnect:
            result = connector.get_ohlcv("EURUSD", "15m", 10)

        mock_reconnect.assert_not_called()
        assert result.empty

    def test_reconnect_on_ipc_error_get_current_price(self):
        """get_current_price: None + IPC-Fehler → Reconnect + Retry."""
        connector = _make_connector()
        connector._connected = True

        tick = SimpleNamespace(bid=1.1000, ask=1.1002, time=1700000000)
        call_count = {"n": 0}

        def fake_tick(symbol):
            call_count["n"] += 1
            return None if call_count["n"] == 1 else tick

        _mt5_mock.symbol_info_tick.side_effect = fake_tick
        _mt5_mock.last_error.return_value = (-10001, "IPC send failed")

        with patch.object(connector, "_try_reconnect", return_value=True):
            result = connector.get_current_price("EURUSD")

        assert result != {}
        assert result["bid"] == 1.1000

    def test_reconnect_debounced_logging(self):
        """10 IPC-Fehler hintereinander → nur 1 Log-Eintrag."""
        connector = _make_connector()
        connector._connected = True
        connector._last_ipc_log = None

        with patch.object(connector, "_try_reconnect", return_value=False):
            with patch("data.mt5_connector.logger") as mock_logger:
                for _ in range(10):
                    connector._log_ipc_error_debounced("EURUSD")

        assert mock_logger.error.call_count == 1

    def test_try_reconnect_sets_connected_false_on_failure(self):
        """_try_reconnect gibt False zurück und setzt _connected=False nach 3 Fehlversuchen."""
        connector = _make_connector()
        connector._connected = True

        with patch.object(connector, "connect", return_value=False):
            with patch("data.mt5_connector.time") as mock_time:
                mock_time.sleep = lambda x: None
                result = connector._try_reconnect()

        assert result is False
        assert connector._connected is False

    def test_is_ipc_error(self):
        """_is_ipc_error erkennt -10001, -10002, -10003 korrekt."""
        connector = _make_connector()
        assert connector._is_ipc_error(-10001) is True
        assert connector._is_ipc_error(-10002) is True
        assert connector._is_ipc_error(-10003) is True
        assert connector._is_ipc_error(-1) is False
        assert connector._is_ipc_error(0) is False


class TestGetDealByTicket:
    def test_returns_none_when_not_connected(self):
        """get_deal_by_ticket gibt None zurück wenn nicht verbunden."""
        connector = _make_connector()
        connector._connected = False
        result = connector.get_deal_by_ticket(12345)
        assert result is None

    def test_returns_deal_data_on_success(self):
        """get_deal_by_ticket liefert dict mit price und profit."""
        connector = _make_connector()
        connector._connected = True

        fake_deal = SimpleNamespace(price=1.1050, profit=25.0, time=1700000000)
        _mt5_mock.history_deals_get.return_value = [fake_deal]
        _mt5_mock.history_deals_get.side_effect = None

        result = connector.get_deal_by_ticket(12345)

        assert result is not None
        assert result["price"] == 1.1050
        assert result["profit"] == 25.0
        assert "time" in result

    def test_returns_none_when_no_deals_found(self):
        """get_deal_by_ticket gibt None zurück wenn keine Deals gefunden."""
        connector = _make_connector()
        connector._connected = True

        _mt5_mock.history_deals_get.return_value = []
        _mt5_mock.history_deals_get.side_effect = None

        result = connector.get_deal_by_ticket(99999)
        assert result is None

    def test_returns_none_on_mt5_error(self):
        """get_deal_by_ticket gibt None zurück bei MT5-Fehler."""
        connector = _make_connector()
        connector._connected = True

        _mt5_mock.history_deals_get.return_value = None
        _mt5_mock.history_deals_get.side_effect = None

        result = connector.get_deal_by_ticket(12345)
        assert result is None


class TestDiagnose:
    def test_diagnose_returns_dict_with_required_keys(self, tmp_path):
        """diagnose() liefert dict mit allen erwarteten Keys."""
        cfg = SimpleNamespace(mt5_common_files_path=str(tmp_path), output_dir=str(tmp_path))
        connector = _make_connector(config=cfg)

        result = connector.diagnose()

        assert "mt5_connected" in result
        assert "common_files_path" in result
        assert "common_files_path_exists" in result
        assert "autotrading_available" in result
        assert result["mt5_connected"] is False  # nicht verbunden
