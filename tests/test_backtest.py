"""Tests for cli/backtest.py core logic — no network calls."""

import datetime
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from cli.backtest import (
    _get_trading_days,
    _build_backtest_json,
    _compute_performance,
    _format_backtest_text,
)


# ------------------------------------------------------------------
# _get_trading_days
# ------------------------------------------------------------------


class TestGetTradingDays:
    @patch("tradingagents.dataflows.a_share_calendar.is_trade_day", side_effect=ImportError)
    def test_basic_weekday_range(self, _mock):
        """Without calendar, returns all weekdays in range."""
        days = _get_trading_days("2026-05-04", "2026-05-08")
        # May 4 Mon, 5 Tue, 6 Wed, 7 Thu, 8 Fri = 5 weekdays
        assert len(days) == 5
        assert "2026-05-04" in days
        assert "2026-05-08" in days

    @patch("tradingagents.dataflows.a_share_calendar.is_trade_day", side_effect=ImportError)
    def test_weekend_exclusion(self, _mock):
        """Saturdays and Sundays should be excluded in fallback mode."""
        days = _get_trading_days("2026-05-09", "2026-05-10")  # Sat, Sun
        assert len(days) == 0

    @patch("tradingagents.dataflows.a_share_calendar.is_trade_day", side_effect=ImportError)
    def test_single_day(self, _mock):
        days = _get_trading_days("2026-05-08", "2026-05-08")  # Friday
        assert len(days) == 1
        assert "2026-05-08" in days

    @patch("tradingagents.dataflows.a_share_calendar.is_trade_day", side_effect=ImportError)
    def test_preserves_date_order(self, _mock):
        days = _get_trading_days("2026-05-04", "2026-05-06")
        assert days == ["2026-05-04", "2026-05-05", "2026-05-06"]

    @patch("tradingagents.dataflows.a_share_calendar.is_trade_day", side_effect=ImportError)
    def test_fallback_when_calendar_unavailable(self, _mock):
        """When trading calendar import fails, falls back to weekdays."""
        days = _get_trading_days("2026-05-04", "2026-05-06")
        assert len(days) == 3


# ------------------------------------------------------------------
# _compute_performance
# ------------------------------------------------------------------


class TestComputePerformance:
    def test_empty_results(self):
        perf = _compute_performance([])
        assert perf["total_return_pct"] == 0.0
        assert perf["win_rate_pct"] == 0.0
        assert perf["avg_holding_return_pct"] == 0.0

    def test_all_buy_decisions(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy", "raw_return": 0.01},
            {"date": "2026-05-05", "status": "completed", "decision": "buy", "raw_return": 0.02},
            {"date": "2026-05-06", "status": "completed", "decision": "buy", "raw_return": -0.005},
        ]
        perf = _compute_performance(results)
        assert perf["win_rate_pct"] == 100.0  # all buys
        assert perf["total_return_pct"] == 2.5  # (0.01+0.02-0.005)*100

    def test_mixed_decisions(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy", "raw_return": 0.03},
            {"date": "2026-05-05", "status": "completed", "decision": "hold", "raw_return": 0.0},
            {"date": "2026-05-06", "status": "completed", "decision": "sell", "raw_return": -0.01},
        ]
        perf = _compute_performance(results)
        assert perf["win_rate_pct"] == 33.33  # 1 buy / 3 total
        assert perf["total_return_pct"] == 2.0

    def test_no_returns_field(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "hold"},
            {"date": "2026-05-05", "status": "completed", "decision": "hold"},
        ]
        perf = _compute_performance(results)
        assert perf["win_rate_pct"] == 0.0
        assert perf["total_return_pct"] == 0.0

    def test_zero_returns_filtered_from_avg(self):
        """Zero returns should be excluded from avg_holding_return_pct."""
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy", "raw_return": 0.05},
            {"date": "2026-05-05", "status": "completed", "decision": "hold", "raw_return": 0.0},
        ]
        perf = _compute_performance(results)
        # avg should be 5% (only the non-zero return counts)
        assert perf["avg_holding_return_pct"] == 5.0


# ------------------------------------------------------------------
# _build_backtest_json
# ------------------------------------------------------------------


class TestBuildBacktestJson:
    def test_basic_json_output(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy", "raw_return": 0.01},
            {"date": "2026-05-05", "status": "completed", "decision": "hold", "raw_return": 0.0},
            {"date": "2026-05-06", "status": "completed", "decision": "sell", "raw_return": -0.005},
        ]
        result = _build_backtest_json("600519", "2026-05-04", "2026-05-06", 3, results)
        data = json.loads(result)
        assert data["ticker"] == "600519"
        assert data["total_trading_days"] == 3
        assert data["analyzed_days"] == 3
        assert data["decisions"] == {"buy": 1, "hold": 1, "sell": 1}

    def test_with_errors(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy"},
            {"date": "2026-05-05", "status": "error", "error": "network timeout"},
        ]
        result = _build_backtest_json("600519", "2026-05-04", "2026-05-05", 2, results)
        data = json.loads(result)
        assert data["analyzed_days"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["error"] == "network timeout"

    def test_json_serializable(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy", "raw_return": 0.03},
        ]
        result = _build_backtest_json("600519", "2026-05-04", "2026-05-04", 1, results)
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_decision_case_insensitive(self):
        """Decisions should be normalized to lowercase."""
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "BUY"},
            {"date": "2026-05-05", "status": "completed", "decision": "Buy"},
            {"date": "2026-05-06", "status": "completed", "decision": "HOLD"},
        ]
        result = _build_backtest_json("600519", "2026-05-04", "2026-05-06", 3, results)
        data = json.loads(result)
        assert data["decisions"]["buy"] == 2
        assert data["decisions"]["hold"] == 1
        assert data["decisions"]["sell"] == 0


# ------------------------------------------------------------------
# _format_backtest_text
# ------------------------------------------------------------------


class TestFormatBacktestText:
    def test_basic_text_output(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy"},
            {"date": "2026-05-05", "status": "completed", "decision": "hold"},
        ]
        result = _format_backtest_text("600519", "2026-05-04", "2026-05-05", 2, results)
        assert "600519" in result
        assert "2026-05-04" in result
        assert "2026-05-05" in result
        assert "买入 (Buy)" in result
        assert "持有 (Hold)" in result

    def test_text_with_errors(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy"},
            {"date": "2026-05-05", "status": "error", "error": "connection refused"},
        ]
        result = _format_backtest_text("000001", "2026-05-04", "2026-05-05", 2, results)
        assert "失败" in result
        assert "connection refused" in result
        assert "已分析" in result

    def test_all_sell_decisions(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "sell"},
            {"date": "2026-05-05", "status": "completed", "decision": "sell"},
        ]
        result = _format_backtest_text("600519", "2026-05-04", "2026-05-05", 2, results)
        assert "卖出 (Sell)" in result

    def test_performance_section_present(self):
        results = [
            {"date": "2026-05-04", "status": "completed", "decision": "buy", "raw_return": 0.01},
        ]
        result = _format_backtest_text("600519", "2026-05-04", "2026-05-04", 1, results)
        assert "绩效指标" in result
        assert "累积收益率" in result
        assert "胜率" in result


# ------------------------------------------------------------------
# CLI registration smoke test
# ------------------------------------------------------------------


class TestCLIRegistration:
    def test_commands_registered(self):
        """Verify backtest command is registered in cli/main.py."""
        from cli.main import app
        commands = [cmd.name for cmd in app.registered_commands]
        assert "backtest" in commands
        assert "portfolio" in commands
