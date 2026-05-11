"""Tests for cross-position correlation & hedge analysis."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
import numpy as np


_POSITIONS = [
    {"symbol": "600519", "quantity": 100, "cost_price": 1500.0, "current_price": 1580.0},
    {"symbol": "000858", "quantity": 500, "cost_price": 140.0, "current_price": 145.0},
    {"symbol": "601318", "quantity": 200, "cost_price": 50.0, "current_price": 55.0},
]


def _make_returns(*series):
    """Create mock return DataFrames from lists."""
    dfs = {}
    for sym, vals in series:
        df = pd.DataFrame({"收盘": [100 + i for i in range(len(vals))]})
        returns = pd.Series(vals)
        df["return"] = returns
        dfs[sym] = df
    return dfs


class TestCorrelationRisk:
    """Tests for assess_correlation_risk."""

    def test_single_position_returns_none(self):
        from tradingagents.dataflows.position_risk import assess_correlation_risk
        result = assess_correlation_risk([{"symbol": "X", "quantity": 1}])
        assert result["risk_level"] == "none"

    def test_high_correlation_detected(self):
        from tradingagents.dataflows.position_risk import assess_correlation_risk

        ret_a = pd.Series([0.01, 0.02, 0.015, 0.018, 0.022] * 12)  # high corr
        ret_b = pd.Series([0.012, 0.019, 0.016, 0.017, 0.021] * 12)

        df_a = pd.DataFrame({"收盘": [100 + i for i in range(60)]})
        df_a["return"] = ret_a
        df_b = pd.DataFrame({"收盘": [100 + i for i in range(60)]})
        df_b["return"] = ret_b

        with patch("tradingagents.dataflows.position_risk._get_stock_history") as mock_hist:
            mock_hist.side_effect = lambda s, d: {"A": df_a, "B": df_b}.get(s)
            result = assess_correlation_risk([
                {"symbol": "A", "quantity": 1}, {"symbol": "B", "quantity": 1}
            ])
            assert len(result["correlation_matrix"]) == 1
            corr = result["correlation_matrix"]["A-B"]
            assert corr > 0.5  # should be positively correlated

    def test_no_correlation_if_no_history(self):
        from tradingagents.dataflows.position_risk import assess_correlation_risk
        with patch("tradingagents.dataflows.position_risk._get_stock_history", return_value=None):
            result = assess_correlation_risk(_POSITIONS)
            assert result["risk_level"] == "low"


class TestHedgeDetection:
    """Tests for detect_hedge_opportunities."""

    def test_negative_correlation_is_hedge(self):
        from tradingagents.dataflows.position_risk import detect_hedge_opportunities

        ret_a = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02] * 12)
        ret_b = pd.Series([-0.015, 0.02, -0.01, 0.015, -0.025] * 12)  # inverse

        df_a = pd.DataFrame({"收盘": [100 + i for i in range(60)]})
        df_a["return"] = ret_a
        df_b = pd.DataFrame({"收盘": [100 + i for i in range(60)]})
        df_b["return"] = ret_b

        with patch("tradingagents.dataflows.position_risk._get_stock_history") as mock_hist:
            mock_hist.side_effect = lambda s, d: {"A": df_a, "B": df_b}.get(s)
            result = detect_hedge_opportunities([
                {"symbol": "A", "quantity": 1}, {"symbol": "B", "quantity": 1}
            ])
            assert len(result["hedge_pairs"]) >= 1

    def test_no_hedge_when_positive_correlation(self):
        from tradingagents.dataflows.position_risk import detect_hedge_opportunities

        ret_a = pd.Series([0.01, 0.02, 0.015] * 20)
        ret_b = pd.Series([0.012, 0.019, 0.016] * 20)

        df_a = pd.DataFrame({"收盘": [100 + i for i in range(60)]})
        df_a["return"] = ret_a
        df_b = pd.DataFrame({"收盘": [100 + i for i in range(60)]})
        df_b["return"] = ret_b

        with patch("tradingagents.dataflows.position_risk._get_stock_history") as mock_hist:
            mock_hist.side_effect = lambda s, d: {"A": df_a, "B": df_b}.get(s)
            result = detect_hedge_opportunities([
                {"symbol": "A", "quantity": 1}, {"symbol": "B", "quantity": 1}
            ])
            assert len(result["hedge_pairs"]) == 0
