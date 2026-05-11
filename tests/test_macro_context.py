"""Tests for macro_context.py."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_akshare():
    """Mock all akshare calls to avoid real network."""
    fake_ak = MagicMock()
    with patch("tradingagents.dataflows.macro_context.ak", fake_ak):
        yield fake_ak


def _fake_us_indices() -> pd.DataFrame:
    return pd.DataFrame([
        {"代码": ".INX", "名称": "S&P 500", "最新价": 5800.0, "涨跌幅": 0.5},
        {"代码": ".IXIC", "名称": "Nasdaq", "最新价": 18200.0, "涨跌幅": 0.8},
        {"代码": ".DJI", "名称": "Dow Jones", "最新价": 42000.0, "涨跌幅": -0.2},
    ])


def _fake_fx() -> pd.DataFrame:
    return pd.DataFrame([
        {"货币对": "美元/人民币", "最新价": 6.92, "涨跌额": -0.01, "涨跌幅": -0.14},
    ])


def _fake_commodities() -> pd.DataFrame:
    return pd.DataFrame([
        {"名称": "COMEX黄金", "最新价": 2350.0, "涨跌幅": 0.3},
        {"名称": "NYMEX原油", "最新价": 78.5, "涨跌幅": -1.2},
    ])


def _fake_vix() -> pd.DataFrame:
    return pd.DataFrame([
        {"名称": "VIX", "最新价": 14.5, "涨跌幅": -0.5},
    ])


def _fake_northbound() -> pd.DataFrame:
    return pd.DataFrame([
        {"北向资金-净流入": 3.5e8, "北向资金-买入成交额": 50e8, "北向资金-卖出成交额": 46.5e8},
    ])


def _fake_bond() -> pd.DataFrame:
    return pd.DataFrame([
        {"期限": "10年", "收益率": 2.35, "涨跌BP": -1.2},
    ])


class TestMacroContext:
    """Tests for fetch_macro_context."""

    def test_all_sections_present(self, mock_akshare):
        mock_akshare.index_us_stock_sina.return_value = _fake_us_indices()
        mock_akshare.fx_spot_quote.return_value = _fake_fx()
        mock_akshare.futures_foreign_commodity_realtime.return_value = _fake_commodities()
        mock_akshare.index_global_spot_em.return_value = _fake_vix()
        mock_akshare.stock_hsgt_fund_flow_summary_em.return_value = _fake_northbound()
        mock_akshare.bond_china_yield.return_value = _fake_bond()

        from tradingagents.dataflows.macro_context import fetch_macro_context
        result = fetch_macro_context()
        assert "美股" in result
        assert "汇率" in result
        assert "大宗" in result
        assert "VIX" in result
        assert "北向" in result
        assert "国债" in result

    def test_us_indices_format(self, mock_akshare):
        mock_akshare.index_us_stock_sina.return_value = _fake_us_indices()
        from tradingagents.dataflows.macro_context import _fetch_us_indices
        result = _fetch_us_indices()
        assert "S&P" in result or "标普" in result or "INX" in result or "5800" in result

    def test_bond_yield_format(self, mock_akshare):
        mock_akshare.bond_china_yield.return_value = _fake_bond()
        from tradingagents.dataflows.macro_context import _fetch_bond_yield
        result = _fetch_bond_yield()
        assert "10Y" in result or "10年" in result or "2.35" in result

    def test_graceful_degradation(self, mock_akshare):
        """All APIs return empty, should still return structured output."""
        for attr in dir(mock_akshare):
            if not attr.startswith("_"):
                setattr(mock_akshare, attr, MagicMock(return_value=pd.DataFrame()))

        from tradingagents.dataflows.macro_context import fetch_macro_context
        result = fetch_macro_context()
        assert len(result) > 0
        assert "——" in result  # graceful missing marker

    def test_output_length_cap(self, mock_akshare):
        mock_akshare.index_us_stock_sina.return_value = _fake_us_indices()
        mock_akshare.fx_spot_quote.return_value = _fake_fx()
        mock_akshare.futures_foreign_commodity_realtime.return_value = _fake_commodities()
        mock_akshare.index_global_spot_em.return_value = _fake_vix()
        mock_akshare.stock_hsgt_fund_flow_summary_em.return_value = _fake_northbound()
        mock_akshare.bond_china_yield.return_value = _fake_bond()

        from tradingagents.dataflows.macro_context import fetch_macro_context
        result = fetch_macro_context()
        assert len(result) <= 1300  # generous cap check
