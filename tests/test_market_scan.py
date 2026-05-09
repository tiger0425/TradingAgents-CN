"""Tests for cli/market_scan.py core logic — no network calls."""

import json
import pytest
import pandas as pd
from cli.market_scan import (
    _sanitize_float,
    _build_stock_entry,
    _determine_market_status,
    _get_top_gainers,
    _get_top_losers,
    _get_top_volume,
)


# ---------------------------------------------------------------------------
# _sanitize_float
# ---------------------------------------------------------------------------

class TestSanitizeFloat:
    def test_valid_float(self):
        assert _sanitize_float(3.14) == 3.14

    def test_valid_int(self):
        assert _sanitize_float(42) == 42.0

    def test_valid_string_float(self):
        assert _sanitize_float("3.14") == 3.14

    def test_none_value(self):
        assert _sanitize_float(None) is None

    def test_invalid_string(self):
        assert _sanitize_float("abc") is None

    def test_empty_string(self):
        assert _sanitize_float("") is None

    def test_nan_string(self):
        assert _sanitize_float("NaN") is None

    def test_zero(self):
        assert _sanitize_float(0.0) == 0.0

    def test_negative(self):
        assert _sanitize_float(-5.5) == -5.5


# ---------------------------------------------------------------------------
# _build_stock_entry
# ---------------------------------------------------------------------------

class TestBuildStockEntry:
    def _make_row(self, code: str, name: str, price: float, change: float,
                   change_pct: float, volume: float = 10000, amount: float = 50000):
        return pd.Series({
            "代码": code,
            "名称": name,
            "最新价": price,
            "涨跌额": change,
            "涨跌幅": change_pct,
            "成交量": volume,
            "成交额": amount,
        })

    def test_standard_entry(self):
        row = self._make_row("sh600519", "贵州茅台", 1580.0, -5.0, -0.32)
        entry = _build_stock_entry(row)
        assert entry["ticker"] == "600519"
        assert entry["name"] == "贵州茅台"
        assert entry["price"] == 1580.0
        assert entry["change"] == -5.0
        assert entry["change_pct"] == -0.32

    def test_shenzhen_code(self):
        row = self._make_row("sz000858", "五粮液", 120.0, 2.0, 1.69)
        entry = _build_stock_entry(row)
        assert entry["ticker"] == "000858"

    def test_beijing_code(self):
        row = self._make_row("bj830799", "某某北交所", 50.0, 1.0, 2.0)
        entry = _build_stock_entry(row)
        assert entry["ticker"] == "830799"

    def test_missing_optional_fields(self):
        row = pd.Series({"代码": "sh600519", "名称": "贵州茅台"})
        entry = _build_stock_entry(row)
        assert entry["ticker"] == "600519"
        assert entry["name"] == "贵州茅台"
        assert entry["price"] is None
        assert entry["change"] is None
        assert entry["change_pct"] is None


# ---------------------------------------------------------------------------
# _determine_market_status
# ---------------------------------------------------------------------------

class TestDetermineMarketStatus:
    def _make_spot_df(self, timestamp: str = "") -> pd.DataFrame:
        cols = {"时间戳": timestamp, "代码": "sh600519", "名称": "贵州茅台"}
        return pd.DataFrame([cols])

    def test_empty_df_returns_unknown(self):
        assert _determine_market_status(None) == "unknown"
        assert _determine_market_status(pd.DataFrame()) == "unknown"

    def test_df_without_timestamp_returns_unknown(self):
        df = pd.DataFrame([{"代码": "sh600519", "名称": "贵州茅台"}])
        result = _determine_market_status(df)
        assert result in ("open", "closed", "unknown")

    def test_df_with_timestamp_returns_valid_status(self):
        df = self._make_spot_df("2026-05-09 14:30:00")
        result = _determine_market_status(df)
        assert result in ("open", "closed")


# ---------------------------------------------------------------------------
# _get_top_gainers
# ---------------------------------------------------------------------------

class TestGetTopGainers:
    def _make_spot_df(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"代码": "sh600001", "名称": "股票A", "最新价": 10.0, "涨跌额": 1.0, "涨跌幅": 10.0, "成交量": 1000, "成交额": 5000},
            {"代码": "sz000002", "名称": "股票B", "最新价": 20.0, "涨跌额": 1.5, "涨跌幅": 8.0, "成交量": 2000, "成交额": 10000},
            {"代码": "sh600003", "名称": "股票C", "最新价": 30.0, "涨跌额": -1.0, "涨跌幅": -5.0, "成交量": 3000, "成交额": 15000},
            {"代码": "sz000004", "名称": "股票D", "最新价": 40.0, "涨跌额": -2.0, "涨跌幅": -3.0, "成交量": 4000, "成交额": 20000},
        ])

    def test_top_n_gainers(self):
        df = self._make_spot_df()
        result = _get_top_gainers(df, 2)
        assert len(result) == 2
        assert result[0]["ticker"] == "600001"  # 10% gain
        assert result[1]["ticker"] == "000002"  # 8% gain

    def test_top_n_larger_than_data(self):
        df = self._make_spot_df()
        result = _get_top_gainers(df, 100)
        assert len(result) == 4  # all 4 stocks

    def test_empty_df(self):
        df = pd.DataFrame()
        result = _get_top_gainers(df, 10)
        assert result == []

    def test_missing_column(self):
        df = pd.DataFrame([{"代码": "sh600001", "名称": "股票A"}])
        result = _get_top_gainers(df, 10)
        assert result == []

    def test_nan_in_change_pct(self):
        df = pd.DataFrame([
            {"代码": "sh600001", "名称": "A", "最新价": 10.0, "涨跌额": 1.0, "涨跌幅": None, "成交量": 1000, "成交额": 5000},
            {"代码": "sh600002", "名称": "B", "最新价": 20.0, "涨跌额": 1.5, "涨跌幅": 5.0, "成交量": 2000, "成交额": 10000},
        ])
        result = _get_top_gainers(df, 5)
        assert len(result) == 1
        assert result[0]["ticker"] == "600002"


# ---------------------------------------------------------------------------
# _get_top_losers
# ---------------------------------------------------------------------------

class TestGetTopLosers:
    def _make_spot_df(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"代码": "sh600001", "名称": "股票A", "最新价": 10.0, "涨跌额": 1.0, "涨跌幅": 10.0, "成交量": 1000, "成交额": 5000},
            {"代码": "sz000002", "名称": "股票B", "最新价": 20.0, "涨跌额": 1.5, "涨跌幅": 8.0, "成交量": 2000, "成交额": 10000},
            {"代码": "sh600003", "名称": "股票C", "最新价": 30.0, "涨跌额": -1.0, "涨跌幅": -5.0, "成交量": 3000, "成交额": 15000},
            {"代码": "sz000004", "名称": "股票D", "最新价": 40.0, "涨跌额": -2.0, "涨跌幅": -10.0, "成交量": 4000, "成交额": 20000},
        ])

    def test_top_n_losers(self):
        df = self._make_spot_df()
        result = _get_top_losers(df, 2)
        assert len(result) == 2
        assert result[0]["ticker"] == "000004"  # -10% (biggest loser)
        assert result[1]["ticker"] == "600003"  # -5%

    def test_empty_df(self):
        df = pd.DataFrame()
        result = _get_top_losers(df, 10)
        assert result == []

    def test_missing_column(self):
        df = pd.DataFrame([{"代码": "sh600001", "名称": "股票A"}])
        result = _get_top_losers(df, 10)
        assert result == []


# ---------------------------------------------------------------------------
# _get_top_volume
# ---------------------------------------------------------------------------

class TestGetTopVolume:
    def _make_spot_df(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"代码": "sh600001", "名称": "股票A", "最新价": 10.0, "涨跌额": 1.0, "涨跌幅": 5.0, "成交量": 1000, "成交额": 5000},
            {"代码": "sz000002", "名称": "股票B", "最新价": 20.0, "涨跌额": 1.5, "涨跌幅": 8.0, "成交量": 5000, "成交额": 10000},
            {"代码": "sh600003", "名称": "股票C", "最新价": 30.0, "涨跌额": -1.0, "涨跌幅": -5.0, "成交量": 3000, "成交额": 15000},
        ])

    def test_top_n_volume(self):
        df = self._make_spot_df()
        result = _get_top_volume(df, 2)
        assert len(result) == 2
        assert result[0]["ticker"] == "000002"  # volume: 5000
        assert result[1]["ticker"] == "600003"  # volume: 3000

    def test_empty_df(self):
        df = pd.DataFrame()
        result = _get_top_volume(df, 10)
        assert result == []

    def test_missing_column(self):
        df = pd.DataFrame([{"代码": "sh600001", "名称": "股票A"}])
        result = _get_top_volume(df, 10)
        assert result == []

    def test_nan_in_volume(self):
        df = pd.DataFrame([
            {"代码": "sh600001", "名称": "A", "最新价": 10.0, "涨跌额": 1.0, "涨跌幅": 5.0, "成交量": None, "成交额": 5000},
            {"代码": "sz000002", "名称": "B", "最新价": 20.0, "涨跌额": 1.5, "涨跌幅": 8.0, "成交量": 5000, "成交额": 10000},
        ])
        result = _get_top_volume(df, 5)
        assert len(result) == 1
        assert result[0]["ticker"] == "000002"


# ---------------------------------------------------------------------------
# CLI registration smoke test
# ---------------------------------------------------------------------------

class TestCLIRegistration:
    def test_market_scan_command_registered(self):
        from cli.main import app
        names = [c.name for c in app.registered_commands if c.name is not None]
        assert "market-scan" in names

    def test_market_scan_import(self):
        from cli.market_scan import market_scan
        assert callable(market_scan)
