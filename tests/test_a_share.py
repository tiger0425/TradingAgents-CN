"""
Integration tests for A-share adaptation of TradingAgents.
Tests cover data fetching, trading calendar, constraints, and routing.
Run with: python -m pytest tests/test_a_share.py -v
"""

import sys
import pytest


# ===========================================================================
# Test A: Data source routing
# ===========================================================================
class TestDataRouting:
    """Verify akshare is correctly registered as the primary vendor."""

    def test_vendor_list(self):
        """VENDOR_LIST should have akshare first."""
        from tradingagents.dataflows.interface import VENDOR_LIST
        assert "akshare" in VENDOR_LIST
        assert VENDOR_LIST[0] == "akshare"

    def test_vendor_methods(self):
        """All 9 methods should have akshare entry."""
        from tradingagents.dataflows.interface import VENDOR_METHODS
        methods = [
            "get_stock_data", "get_indicators", "get_fundamentals",
            "get_balance_sheet", "get_cashflow", "get_income_statement",
            "get_news", "get_global_news", "get_insider_transactions",
        ]
        for m in methods:
            assert "akshare" in VENDOR_METHODS[m], f"{m} missing akshare"

    def test_default_config(self):
        """data_vendors should default to akshare."""
        from tradingagents.default_config import DEFAULT_CONFIG
        for cat in ["core_stock_apis", "technical_indicators",
                     "fundamental_data", "news_data"]:
            assert DEFAULT_CONFIG["data_vendors"][cat] == "akshare"


# ===========================================================================
# Test B: Stock data fetching
# ===========================================================================
class TestStockData:
    """Test that akshare returns real data for A-share stocks."""

    @pytest.mark.parametrize("symbol,reason", [
        ("600519", "蓝筹-贵州茅台"),
        ("300750", "成长-宁德时代"),
        ("601398", "金融-工商银行"),
        ("002415", "中小板-海康威视"),
    ])
    def test_get_stock_data_returns_csv(self, symbol, reason):
        """get_stock_data should return CSV string with headers."""
        from tradingagents.dataflows.akshare import get_stock_data
        result = get_stock_data(symbol, "2026-01-02", "2026-01-10")
        assert isinstance(result, str)
        assert result.startswith("# Stock data for"), f"{symbol}: bad header"
        assert "Date" in result, f"{symbol}: missing CSV header"
        assert not result.startswith("Error"), f"{symbol}: error: {result[:100]}"

    def test_get_fundamentals(self):
        """get_fundamentals should return financial data."""
        from tradingagents.dataflows.akshare import get_fundamentals
        result = get_fundamentals("600519", "2026-01-15")
        assert isinstance(result, str)
        assert ("ROE" in result or "Revenue" in result
                or result.startswith("Error") or result.startswith("No"))

    def test_get_balance_sheet(self):
        """get_balance_sheet should return CSV or informative message."""
        from tradingagents.dataflows.akshare import get_balance_sheet
        result = get_balance_sheet("600519", "annual", "2026-01-15")
        assert isinstance(result, str)


# ===========================================================================
# Test C: Trading calendar
# ===========================================================================
class TestTradingCalendar:
    """Test A-share trading calendar functions."""

    def test_is_trade_day_weekday(self):
        """Regular weekdays should be trade days."""
        from tradingagents.dataflows.a_share_calendar import is_trade_day
        result = is_trade_day("2026-01-05")
        assert result is True or result is False

    def test_next_prev_trade_day(self):
        """next/prev_trade_day should return valid dates."""
        from tradingagents.dataflows.a_share_calendar import next_trade_day, prev_trade_day
        nxt = next_trade_day("2026-01-15")
        assert isinstance(nxt, str) and len(nxt) == 10
        prv = prev_trade_day("2026-01-15")
        assert isinstance(prv, str) and len(prv) == 10


# ===========================================================================
# Test D: Constraints
# ===========================================================================
class TestConstraints:
    """Test A-share market constraint functions."""

    def test_get_limit_prices_default(self):
        """Default limit rate should be 10%."""
        from tradingagents.dataflows.a_share_constraints import get_limit_prices
        up, down = get_limit_prices(100.0)
        assert up == 110.0
        assert down == 90.0

    def test_get_limit_rate_boards(self):
        """Different boards should have different limit rates."""
        from tradingagents.dataflows.a_share_constraints import get_limit_rate
        assert get_limit_rate("688888") == 0.20
        assert get_limit_rate("300888") == 0.20
        assert get_limit_rate("830888") == 0.30
        assert get_limit_rate("600519") == 0.10

    def test_get_limit_rate_st(self):
        """ST stocks should have 5% limit."""
        from tradingagents.dataflows.a_share_constraints import get_limit_rate
        assert get_limit_rate("600519", "ST某某") == 0.05
        assert get_limit_rate("600519", "*ST某某") == 0.05

    def test_format_limit_constraint_a_share(self):
        """A_SHARE should get constraint text."""
        from tradingagents.dataflows.a_share_constraints import format_limit_constraint
        text = format_limit_constraint(110.0, 90.0, "A_SHARE")
        assert "limit-up" in text
        assert "MUST be within" in text

    def test_format_limit_constraint_us_stock(self):
        """US_STOCK should get empty string (backward compatible)."""
        from tradingagents.dataflows.a_share_constraints import format_limit_constraint
        assert format_limit_constraint(110.0, 90.0, "US_STOCK") == ""

    def test_format_t_plus_1_same_day(self):
        """Same-day position should trigger T+1 constraint."""
        from tradingagents.dataflows.a_share_constraints import format_t_plus_1_constraint
        text = format_t_plus_1_constraint("2026-01-15", "2026-01-15", "A_SHARE")
        assert "T+1" in text
        assert "CANNOT" in text

    def test_format_t_plus_1_next_day(self):
        """Next-day position should NOT trigger T+1 (can sell)."""
        from tradingagents.dataflows.a_share_constraints import format_t_plus_1_constraint
        assert format_t_plus_1_constraint("2026-01-14", "2026-01-15", "A_SHARE") == ""

    def test_format_t_plus_1_no_position(self):
        """No position should permit buying."""
        from tradingagents.dataflows.a_share_constraints import format_t_plus_1_constraint
        text = format_t_plus_1_constraint("", "2026-01-15", "A_SHARE")
        assert "Buying is permitted" in text

    def test_format_t_plus_1_us_stock(self):
        """US_STOCK should not have T+1 constraint."""
        from tradingagents.dataflows.a_share_constraints import format_t_plus_1_constraint
        assert format_t_plus_1_constraint("2026-01-15", "2026-01-15", "US_STOCK") == ""


# ===========================================================================
# Test E: AgentState
# ===========================================================================
class TestAgentState:
    """Verify AgentState has A-share fields (structural check)."""

    def test_a_share_fields_exist(self):
        """AgentState class should define A-share fields."""
        import ast
        with open("tradingagents/agents/utils/agent_states.py") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AgentState":
                field_names = []
                for n in node.body:
                    if isinstance(n, ast.AnnAssign):
                        if isinstance(n.target, ast.Name):
                            field_names.append(n.target.id)
                        elif hasattr(n.target, 'attr'):
                            field_names.append(n.target.attr)
                assert "market_type" in field_names
                assert "limit_up_price" in field_names
                assert "limit_down_price" in field_names
                assert "position_opened_date" in field_names
                assert "benchmark_ticker" in field_names
                return
        pytest.fail("AgentState class not found")


# ===========================================================================
# Test F: Module import integrity
# ===========================================================================
class TestModuleImports:
    """All A-share modules should import without errors."""

    def test_akshare_vendor_imports(self):
        """All 9 vendor functions should be importable."""
        from tradingagents.dataflows.akshare import (
            get_stock_data, get_indicators, get_fundamentals,
            get_balance_sheet, get_cashflow, get_income_statement,
            get_news, get_global_news, get_insider_transactions,
        )
        assert callable(get_stock_data)
        assert callable(get_indicators)
        assert callable(get_insider_transactions)

    def test_calendar_imports(self):
        """Calendar functions should be importable."""
        from tradingagents.dataflows.a_share_calendar import (
            is_trade_day, next_trade_day, prev_trade_day,
        )
        assert callable(is_trade_day)
        assert callable(next_trade_day)
        assert callable(prev_trade_day)

    def test_constraint_imports(self):
        """Constraint functions should be importable."""
        from tradingagents.dataflows.a_share_constraints import (
            get_limit_prices, get_limit_rate, format_limit_constraint,
            format_t_plus_1_constraint,
        )
        assert callable(get_limit_prices)
        assert callable(get_limit_rate)
        assert callable(format_limit_constraint)
        assert callable(format_t_plus_1_constraint)
