"""Tests for cli/portfolio.py core logic — no network calls."""

import datetime
import json
import pytest
from unittest.mock import patch, MagicMock

from cli.portfolio import (
    _build_portfolio_json,
    _format_portfolio_text,
    _fetch_spot_prices,
)


# ------------------------------------------------------------------
# _build_portfolio_json
# ------------------------------------------------------------------


class TestBuildPortfolioJson:
    def test_empty_portfolio(self):
        result = _build_portfolio_json(
            holdings=[],
            totals={"total_cost": 0.0, "total_market_value": 0.0, "total_pnl": 0.0, "total_pnl_pct": 0.0},
            concentration={"top1_weight": 0.0, "top3_weight": 0.0, "num_holdings": 0},
            date="2026-05-09",
        )
        data = json.loads(result)
        assert data["total_holdings"] == 0
        assert data["holdings"] == []
        assert data["concentration"]["num_holdings"] == 0

    def test_single_holding(self):
        holdings = [
            {
                "ticker": "600519", "name": "贵州茅台",
                "cost_price": 1580.0, "quantity": 100,
                "current_price": 1620.0, "market_value": 162000.0,
                "pnl_amount": 4000.0, "pnl_pct": 2.53, "weight": 100.0,
            }
        ]
        totals = {"total_cost": 158000.0, "total_market_value": 162000.0,
                  "total_pnl": 4000.0, "total_pnl_pct": 2.53}
        concentration = {"top1_weight": 100.0, "top3_weight": 100.0, "num_holdings": 1}

        result = _build_portfolio_json(holdings, totals, concentration, "2026-05-09")
        data = json.loads(result)
        assert data["total_holdings"] == 1
        assert data["total_pnl"] == 4000.0
        assert data["holdings"][0]["ticker"] == "600519"
        assert data["holdings"][0]["weight"] == 100.0
        assert data["concentration"]["top1_weight"] == 100.0

    def test_multiple_holdings(self):
        holdings = [
            {"ticker": "600519", "name": "茅台", "cost_price": 1580.0, "quantity": 100,
             "current_price": 1620.0, "market_value": 162000.0,
             "pnl_amount": 4000.0, "pnl_pct": 2.53, "weight": 92.57},
            {"ticker": "000858", "name": "五粮液", "cost_price": 120.0, "quantity": 100,
             "current_price": 130.0, "market_value": 13000.0,
             "pnl_amount": 1000.0, "pnl_pct": 8.33, "weight": 7.43},
        ]
        totals = {"total_cost": 170000.0, "total_market_value": 175000.0,
                  "total_pnl": 5000.0, "total_pnl_pct": 2.94}
        concentration = {"top1_weight": 92.57, "top3_weight": 100.0, "num_holdings": 2}

        result = _build_portfolio_json(holdings, totals, concentration, "2026-05-09")
        data = json.loads(result)
        assert len(data["holdings"]) == 2
        assert data["total_pnl"] == 5000.0
        assert data["concentration"]["top1_weight"] == 92.57

    def test_json_serializable(self):
        """All output values must be JSON-serializable."""
        holdings = [
            {"ticker": "600519", "name": "茅台", "cost_price": 1580.0, "quantity": 100,
             "current_price": 1620.0, "market_value": 162000.0,
             "pnl_amount": 4000.0, "pnl_pct": 2.53, "weight": 92.57}
        ]
        totals = {"total_cost": 158000.0, "total_market_value": 162000.0,
                  "total_pnl": 4000.0, "total_pnl_pct": 2.53}
        concentration = {"top1_weight": 100.0, "top3_weight": 100.0, "num_holdings": 1}
        result = _build_portfolio_json(holdings, totals, concentration, "2026-05-09")
        # Verify it parses without error
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_pnl_pct_none_value(self):
        """When pnl_pct is None, it should be serialized as null."""
        holdings = [
            {"ticker": "000001", "name": "测试", "cost_price": 0.0, "quantity": 0,
             "current_price": 10.0, "market_value": 0.0,
             "pnl_amount": 0.0, "pnl_pct": None, "weight": 0.0}
        ]
        totals = {"total_cost": 0.0, "total_market_value": 0.0, "total_pnl": 0.0, "total_pnl_pct": 0.0}
        concentration = {"top1_weight": 0.0, "top3_weight": 0.0, "num_holdings": 1}
        result = _build_portfolio_json(holdings, totals, concentration, "2026-05-09")
        data = json.loads(result)
        assert data["holdings"][0]["pnl_pct"] is None


# ------------------------------------------------------------------
# _format_portfolio_text
# ------------------------------------------------------------------


class TestFormatPortfolioText:
    def test_empty_portfolio(self):
        result = _format_portfolio_text(
            holdings=[],
            totals={},
            concentration={},
            date="2026-05-09",
        )
        assert "(无持仓记录)" in result
        assert "2026-05-09" in result

    def test_single_holding(self):
        holdings = [
            {"ticker": "600519", "name": "茅台", "cost_price": 1580.0, "quantity": 100,
             "current_price": 1620.0, "market_value": 162000.0,
             "pnl_amount": 4000.0, "pnl_pct": 2.53, "weight": 100.0}
        ]
        totals = {"total_cost": 158000.0, "total_market_value": 162000.0,
                  "total_pnl": 4000.0, "total_pnl_pct": 2.53}
        concentration = {"top1_weight": 100.0, "top3_weight": 100.0, "num_holdings": 1}

        result = _format_portfolio_text(holdings, totals, concentration, "2026-05-09")
        assert "600519" in result
        assert "茅台" in result
        assert "1580.00" in result
        assert "1620.00" in result
        assert "4000.00" in result
        assert "2.53%" in result

    def test_multiple_holdings_includes_all_tickers(self):
        holdings = [
            {"ticker": "600519", "name": "茅台", "cost_price": 1580.0, "quantity": 100,
             "current_price": 1620.0, "market_value": 162000.0,
             "pnl_amount": 4000.0, "pnl_pct": 2.53, "weight": 92.57},
            {"ticker": "000858", "name": "五粮液", "cost_price": 120.0, "quantity": 100,
             "current_price": 130.0, "market_value": 13000.0,
             "pnl_amount": 1000.0, "pnl_pct": 8.33, "weight": 7.43},
        ]
        totals = {"total_cost": 170000.0, "total_market_value": 175000.0,
                  "total_pnl": 5000.0, "total_pnl_pct": 2.94}
        concentration = {"top1_weight": 92.57, "top3_weight": 100.0, "num_holdings": 2}

        result = _format_portfolio_text(holdings, totals, concentration, "2026-05-09")
        assert "600519" in result
        assert "000858" in result
        assert "5000.00" in result

    def test_concentration_section(self):
        holdings = [
            {"ticker": "600519", "name": "茅台", "cost_price": 1580.0, "quantity": 100,
             "current_price": 1620.0, "market_value": 162000.0,
             "pnl_amount": 4000.0, "pnl_pct": 2.53, "weight": 92.57},
            {"ticker": "000858", "name": "五粮液", "cost_price": 120.0, "quantity": 100,
             "current_price": 130.0, "market_value": 13000.0,
             "pnl_amount": 1000.0, "pnl_pct": 8.33, "weight": 7.43},
        ]
        totals = {"total_cost": 170000.0, "total_market_value": 175000.0,
                  "total_pnl": 5000.0, "total_pnl_pct": 2.94}
        concentration = {"top1_weight": 92.57, "top3_weight": 100.0, "num_holdings": 2}

        result = _format_portfolio_text(holdings, totals, concentration, "2026-05-09")
        assert "持仓数" in result
        assert "最大仓位占比" in result
        assert "前三大仓位占比" in result
        assert "92.57%" in result

    def test_zero_price_handling(self):
        """Position with zero current price should still display gracefully."""
        holdings = [
            {"ticker": "600519", "name": "茅台", "cost_price": 1580.0, "quantity": 100,
             "current_price": 0.0, "market_value": 0.0,
             "pnl_amount": -158000.0, "pnl_pct": None, "weight": 0.0}
        ]
        totals = {"total_cost": 158000.0, "total_market_value": 0.0,
                  "total_pnl": -158000.0, "total_pnl_pct": -100.0}
        concentration = {"top1_weight": 0.0, "top3_weight": 0.0, "num_holdings": 1}

        result = _format_portfolio_text(holdings, totals, concentration, "2026-05-09")
        # Should not crash
        assert "600519" in result


# ------------------------------------------------------------------
# _fetch_spot_prices
# ------------------------------------------------------------------


class TestFetchSpotPrices:
    @patch("cli.portfolio._AKSHARE_AVAILABLE", False)
    def test_akshare_not_available(self):
        result = _fetch_spot_prices(["600519"])
        assert result == {}

    @patch("cli.portfolio._AKSHARE_AVAILABLE", True)
    @patch("tradingagents.dataflows.akshare.get_current_price")
    def test_akshare_returns_none(self, mock_gcp):
        mock_gcp.return_value = None
        result = _fetch_spot_prices(["600519"])
        assert result == {}

    @patch("cli.portfolio._AKSHARE_AVAILABLE", True)
    @patch("tradingagents.dataflows.akshare.get_current_price")
    def test_akshare_returns_empty_df(self, mock_gcp):
        mock_gcp.return_value = "No real-time data available"
        result = _fetch_spot_prices(["600519"])
        assert result == {}

    @patch("cli.portfolio._AKSHARE_AVAILABLE", True)
    @patch("tradingagents.dataflows.akshare.get_current_price")
    def test_akshare_returns_valid_data(self, mock_gcp):
        mock_gcp.return_value = (
            "# Real-time Quote for 600519 (贵州茅台)\n"
            "**Current Price**: 1620.0\n"
            "**Change**: 20.0 (1.25%)\n"
            "**Open**: 1585.0\n"
            "**High**: 1630.0\n"
            "**Low**: 1575.0\n"
            "**Previous Close**: 1600.0\n"
            "**Volume**: 2850000\n"
            "**Turnover**: 4523000000\n"
        )

        result = _fetch_spot_prices(["600519"])
        assert len(result) == 1
        assert "600519" in result
        assert result["600519"]["name"] == "贵州茅台"
        assert result["600519"]["current_price"] == 1620.0

    @patch("cli.portfolio._AKSHARE_AVAILABLE", True)
    @patch("tradingagents.dataflows.akshare.get_current_price")
    def test_handles_missing_fields(self, mock_gcp):
        mock_gcp.return_value = "# Real-time Quote for 600519 (贵州茅台)\n**Note**: no price data\n"
        result = _fetch_spot_prices(["600519"])
        assert result == {}

    @patch("cli.portfolio._AKSHARE_AVAILABLE", True)
    @patch("tradingagents.dataflows.akshare.get_current_price")
    def test_akshare_raises_exception(self, mock_gcp):
        mock_gcp.side_effect = RuntimeError("network error")
        result = _fetch_spot_prices(["600519"])
        assert result == {}

    @patch("cli.portfolio._AKSHARE_AVAILABLE", True)
    @patch("tradingagents.dataflows.akshare.get_current_price")
    def test_ignores_non_numeric_tickers(self, mock_gcp):
        mock_gcp.return_value = (
            "# Real-time Quote for 600519 (茅台)\n"
            "**Current Price**: 1620.0\n"
            "**Change**: 20.0 (1.25%)\n"
        )
        result = _fetch_spot_prices(["600519"])
        assert len(result) == 1
        assert "600519" in result
