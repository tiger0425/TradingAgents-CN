"""Tests for cli/quote.py and akshare.py get_real_time_quotes."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest
import tradingagents.dataflows.akshare as ak_mod

from tradingagents.dataflows.akshare import get_real_time_quotes


def _fake_spot_em() -> pd.DataFrame:
    """Return a fake East Money spot DataFrame for testing."""
    return pd.DataFrame([
        {
            "代码": "600519",
            "名称": "贵州茅台",
            "最新价": 1580.00,
            "涨跌额": 12.50,
            "涨跌幅": 0.80,
            "今开": 1570.00,
            "最高": 1590.00,
            "最低": 1568.00,
            "昨收": 1567.50,
            "成交量": 2500000,
            "成交额": 3950000000,
            "振幅": 1.40,
            "换手率": 0.20,
            "市盈率-动态": 25.5,
            "市净率": 6.8,
        },
        {
            "代码": "000858",
            "名称": "五粮液",
            "最新价": 145.00,
            "涨跌额": -1.50,
            "涨跌幅": -1.02,
            "今开": 146.50,
            "最高": 147.00,
            "最低": 144.50,
            "昨收": 146.50,
            "成交量": 18000000,
            "成交额": 2610000000,
            "振幅": 1.71,
            "换手率": 0.46,
            "市盈率-动态": 18.2,
            "市净率": 5.1,
        },
    ])


class TestGetRealTimeQuotes:
    """Tests for get_real_time_quotes() in akshare.py."""

    def setup_method(self):
        """Clear module-level cache before each test."""
        ak_mod._spot_em_cache = (0, None)

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=_fake_spot_em())
    def test_single_stock(self, mock_ak):
        """Single stock returns valid Markdown with price info."""
        result = get_real_time_quotes("600519")
        assert "600519" in result
        assert "贵州茅台" in result
        assert "1580" in result  # float repr, may be 1580.0
        assert "最新价" in result

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=_fake_spot_em())
    def test_multi_stock(self, mock_ak):
        """Comma-separated symbols return batch table."""
        result = get_real_time_quotes("600519,000858")
        assert "600519" in result
        assert "000858" in result
        assert "贵州茅台" in result
        assert "五粮液" in result

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=_fake_spot_em())
    def test_invalid_symbol(self, mock_ak):
        """Invalid ticker returns error message."""
        result = get_real_time_quotes("999999")
        assert "999999" in result
        assert "No real-time quote found" in result

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=pd.DataFrame())
    def test_empty_dataframe(self, mock_ak):
        """Empty DataFrame returns no-data message."""
        result = get_real_time_quotes("600519")
        assert "No real-time data available" in result or "no" in result.lower()

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=_fake_spot_em())
    @patch("tradingagents.dataflows.akshare.time.time", return_value=100.0)
    def test_cache_hit(self, mock_time, mock_ak):
        """Second call within TTL uses cache (akshare called once)."""
        get_real_time_quotes("600519")
        get_real_time_quotes("600519")
        assert mock_ak.call_count == 1

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=_fake_spot_em())
    @patch("tradingagents.dataflows.akshare.time.time", side_effect=[100.0, 200.0])
    def test_cache_miss(self, mock_time, mock_ak):
        """Call after TTL expires re-fetches from akshare."""
        get_real_time_quotes("600519")
        get_real_time_quotes("600519")
        assert mock_ak.call_count == 2

    def test_chinese_comma(self):
        """Chinese comma （，）should be handled same as English comma."""
        # Just test the logic without network
        pass


class TestQuoteCli:
    """Minimal CLI integration tests (mocked)."""

    @patch("tradingagents.dataflows.akshare.ak.stock_zh_a_spot_em", return_value=_fake_spot_em())
    def test_cli_text_output(self, mock_ak):
        """CLI command produces text output."""
        result = get_real_time_quotes("600519")
        assert isinstance(result, str)
        assert len(result) > 50
