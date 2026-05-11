"""Tests for trading_plan.py."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


def _sample_position():
    return [{"symbol": "600519", "quantity": 100, "cost_price": 1550.0, "current_price": 1580.0}]


def _sample_multi_positions():
    return [
        {"symbol": "600519", "quantity": 100, "cost_price": 1550.0, "current_price": 1580.0, "name": "贵州茅台"},
        {"symbol": "000858", "quantity": 500, "cost_price": 140.0, "current_price": 145.0, "name": "五粮液"},
        {"symbol": "600036", "quantity": 500, "cost_price": 30.0, "current_price": 28.0, "name": "招商银行"},
    ]


def _mock_history():
    """30 daily OHLCV bars with a clear range."""
    import numpy as np
    base = 100.0
    data = []
    for i in range(30):
        data.append({
            "日期": f"2026-04-{10+i:02d}" if (10+i) <= 30 else f"2026-05-{10+i-30:02d}",
            "开盘": base + i * 0.5,
            "收盘": base + i * 0.5 + np.random.uniform(-2, 2),
            "最高": base + i * 0.5 + abs(np.random.uniform(0, 3)),
            "最低": base + i * 0.5 - abs(np.random.uniform(0, 3)),
        })
    df = pd.DataFrame(data)
    df["收盘"] = [105 + i * 0.3 for i in range(30)]  # steady uptrend
    return df


class TestTradingPlan:
    """Tests for generate_trading_plan."""

    def test_single_position(self):
        from tradingagents.dataflows.trading_plan import generate_trading_plan
        with patch("tradingagents.dataflows.trading_plan._get_history", return_value=_mock_history()):
            result = generate_trading_plan(_sample_position())
            assert "per_position" in result
            assert "summary" in result
            assert len(result["per_position"]) == 1

    def test_action_for_profitable_position(self):
        """Profitable position should suggest reducing or holding."""
        from tradingagents.dataflows.trading_plan import generate_trading_plan
        pos = [{"symbol": "TEST", "quantity": 100, "cost_price": 50.0, "current_price": 100.0}]
        with patch("tradingagents.dataflows.trading_plan._get_history", return_value=_mock_history()):
            result = generate_trading_plan(pos)
            action = result["per_position"][0]["action"]
            assert action == "持有" or action == "减仓"

    def test_action_for_losing_position(self):
        """Position with >8% loss should suggest reducing."""
        from tradingagents.dataflows.trading_plan import generate_trading_plan
        pos = [{"symbol": "TEST", "quantity": 100, "cost_price": 100.0, "current_price": 88.0}]
        with patch("tradingagents.dataflows.trading_plan._get_history", return_value=_mock_history()):
            result = generate_trading_plan(pos)
            action = result["per_position"][0]["action"]
            assert action == "减仓"

    def test_multiple_positions(self):
        from tradingagents.dataflows.trading_plan import generate_trading_plan
        with patch("tradingagents.dataflows.trading_plan._get_history", return_value=_mock_history()):
            result = generate_trading_plan(_sample_multi_positions(), total_portfolio_value=250000)
            assert len(result["per_position"]) == 3

    def test_entry_not_exceed_limit(self):
        """Entry price should be clamped within limit up/down."""
        from tradingagents.dataflows.trading_plan import generate_trading_plan
        from unittest.mock import patch as patch2
        pos = [{"symbol": "600519", "quantity": 100, "cost_price": 1550.0, "current_price": 1580.0}]

        with patch("tradingagents.dataflows.trading_plan._get_history", return_value=_mock_history()):
            with patch("tradingagents.dataflows.a_share_constraints.get_limit_prices", return_value=(1738.0, 1422.0)):
                result = generate_trading_plan(pos)
                entry = result["per_position"][0]["suggested_entry"]
                assert 1422.0 <= entry <= 1738.0

    def test_format_markdown(self):
        from tradingagents.dataflows.trading_plan import generate_trading_plan, format_plan_markdown
        with patch("tradingagents.dataflows.trading_plan._get_history", return_value=_mock_history()):
            plan = generate_trading_plan(_sample_position())
            md = format_plan_markdown(plan)
            assert "操作" in md
            assert "建议买入" in md
            assert "止损" in md
            assert "目标" in md or "目标价" in md


class TestHelpers:
    def test_calc_atr_on_flat_data(self):
        from tradingagents.dataflows.trading_plan import _calc_atr
        import pandas as pd
        df = pd.DataFrame({
            "最高": [101, 102, 101, 103, 102],
            "最低": [99, 98, 99, 97, 98],
            "收盘": [100, 101, 100, 102, 101],
        })
        atr = _calc_atr(df, 3)
        assert atr > 0

    def test_support_resistance(self):
        from tradingagents.dataflows.trading_plan import _calc_support_resistance
        import pandas as pd
        df = pd.DataFrame({
            "收盘": [100, 101, 102, 103, 104],
            "最高": [102, 103, 104, 105, 106],
            "最低": [99, 100, 101, 102, 103],
        })
        sup, res = _calc_support_resistance(df)
        assert sup < res
        assert sup > 0
