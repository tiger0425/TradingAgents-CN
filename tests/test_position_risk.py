"""Tests for position_risk.py risk assessment module."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pytest


def _sample_positions():
    """Sample portfolio positions for testing."""
    return [
        {"symbol": "600519", "quantity": 100, "cost_price": 1500.0, "current_price": 1580.0},
        {"symbol": "000858", "quantity": 500, "cost_price": 140.0, "current_price": 145.0},
        {"symbol": "601318", "quantity": 200, "cost_price": 50.0, "current_price": 55.0},
    ]


def _single_position():
    """Single concentrated position."""
    return [
        {"symbol": "600519", "quantity": 1000, "cost_price": 1500.0, "current_price": 1580.0},
    ]


class TestConcentrationRisk:
    """Tests for assess_concentration_risk."""

    def test_empty_positions(self):
        from tradingagents.dataflows.position_risk import assess_concentration_risk
        result = assess_concentration_risk([])
        assert result["hhi"] == 0

    def test_single_position_max_concentration(self):
        from tradingagents.dataflows.position_risk import assess_concentration_risk
        result = assess_concentration_risk(_single_position())
        assert result["hhi"] == 1.0  # only one position = HHI=1
        assert "非常集中" in result["concentration_level"]

    def test_diversified_positions(self):
        from tradingagents.dataflows.position_risk import assess_concentration_risk
        result = assess_concentration_risk(_sample_positions())
        assert result["hhi"] < 1.0  # diversified
        assert result["hhi"] > 0
        assert result["num_positions"] == 3

    def test_largest_position_identified(self):
        from tradingagents.dataflows.position_risk import assess_concentration_risk
        result = assess_concentration_risk([
            {"symbol": "A", "quantity": 100, "cost_price": 10.0, "current_price": 10.0},
            {"symbol": "B", "quantity": 900, "cost_price": 10.0, "current_price": 10.0},
        ])
        assert result["largest_position"] == "B"
        assert result["largest_weight"] == 90.0  # 9000/10000 = 90%


class TestMarketDropRisk:
    """Tests for assess_market_drop_impact."""

    def test_empty_positions(self):
        from tradingagents.dataflows.position_risk import assess_market_drop_impact
        result = assess_market_drop_impact([], 3.0)
        assert result["total_impact"] == 0

    def test_with_positions(self):
        """Smoke test: returns expected structure."""
        with patch("tradingagents.dataflows.position_risk._calc_beta_from_symbol", return_value=1.0):
            from tradingagents.dataflows.position_risk import assess_market_drop_impact
            result = assess_market_drop_impact(_sample_positions(), 3.0)
            assert result["total_value"] > 0
            assert result["benchmark_drop_pct"] == 3.0
            assert len(result["positions"]) == 3
            assert result["total_impact"] > 0

    def test_high_beta_more_impact(self):
        """Higher beta = larger estimated loss."""
        from tradingagents.dataflows.position_risk import assess_market_drop_impact

        pos = [{"symbol": "TEST", "quantity": 100, "cost_price": 100.0, "current_price": 100.0}]

        with patch("tradingagents.dataflows.position_risk._calc_beta_from_symbol", return_value=2.0):
            result_high = assess_market_drop_impact(pos, 3.0)

        with patch("tradingagents.dataflows.position_risk._calc_beta_from_symbol", return_value=1.0):
            result_low = assess_market_drop_impact(pos, 3.0)

        assert result_high["positions"][0]["est_loss"] > result_low["positions"][0]["est_loss"]


class TestDrawdownRisk:
    """Tests for assess_drawdown."""

    def test_empty_positions(self):
        from tradingagents.dataflows.position_risk import assess_drawdown
        result = assess_drawdown([])
        assert "max_portfolio_drawdown_pct" in result

    def test_with_mocked_data(self):
        """Returns per-position drawdown with mocked history."""
        from tradingagents.dataflows.position_risk import assess_drawdown
        import pandas as pd

        # Mock rising prices (0% drawdown)
        mock_df = pd.DataFrame({"收盘": [100.0, 101.0, 102.0, 103.0, 104.0]})
        mock_df["return"] = mock_df["收盘"].pct_change()

        positions = [{"symbol": "TEST", "quantity": 100, "cost_price": 100.0}]

        with patch("tradingagents.dataflows.position_risk._get_stock_history", return_value=mock_df):
            result = assess_drawdown(positions, 5)
            assert result["max_portfolio_drawdown_pct"] == 0.0

    def test_with_drawdown_data(self):
        """Detects drawdown correctly."""
        from tradingagents.dataflows.position_risk import assess_drawdown
        import pandas as pd

        # Prices that go down 20% from peak
        mock_df = pd.DataFrame({"收盘": [100.0, 80.0, 90.0, 85.0, 95.0]})
        mock_df["return"] = mock_df["收盘"].pct_change()

        positions = [{"symbol": "TEST", "quantity": 100, "cost_price": 100.0}]

        with patch("tradingagents.dataflows.position_risk._get_stock_history", return_value=mock_df):
            result = assess_drawdown(positions, 5)
            assert result["per_position"][0]["max_drawdown_pct"] > 0
            assert result["per_position"][0]["max_drawdown_pct"] == 20.0  # 100→80 = 20%


class TestComprehensive:
    """Test the combined assess_all_risks function."""

    def test_all_risks_structure(self):
        from tradingagents.dataflows.position_risk import assess_all_risks
        with patch("tradingagents.dataflows.position_risk._calc_beta_from_symbol", return_value=1.0):
            with patch("tradingagents.dataflows.position_risk._get_stock_history") as mock_hist:
                import pandas as pd
                mock_hist.return_value = pd.DataFrame({"收盘": [100.0, 99.0, 98.0], "return": [None, -0.01, -0.0101]})

                result = assess_all_risks(_sample_positions())
                assert "market_drop_risk" in result
                assert "market_drop_5pct" in result
                assert "concentration" in result
                assert "drawdown" in result
