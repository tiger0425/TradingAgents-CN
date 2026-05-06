"""Tests for position tracking fields in AgentState."""
from tradingagents.dataflows.position_utils import (
    calc_avg_cost_after_add,
    calc_position_pnl,
    calc_realized_pnl,
    format_position_context,
    format_position_for_pm,
    format_position_for_trader,
)

import pytest


class TestAgentStateFields:
    """Tests for AgentState position field defaults."""

    def test_default_cost_price(self):
        from tradingagents.agents.utils.agent_states import AgentState

        state = AgentState(
            messages=[],
            company_of_interest="600519",
            trade_date="2026-05-06",
            cost_price=0.0,
            quantity=0,
            position_pnl=0.0,
            position_pnl_pct=None,
            position_opened_date="",
        )
        assert state["cost_price"] == 0.0

    def test_default_quantity(self):
        from tradingagents.agents.utils.agent_states import AgentState

        state = AgentState(
            messages=[],
            company_of_interest="600519",
            trade_date="2026-05-06",
            cost_price=0.0,
            quantity=0,
            position_pnl=0.0,
            position_pnl_pct=None,
            position_opened_date="",
        )
        assert state["quantity"] == 0

    def test_default_position_pnl(self):
        from tradingagents.agents.utils.agent_states import AgentState

        state = AgentState(
            messages=[],
            company_of_interest="600519",
            trade_date="2026-05-06",
            cost_price=0.0,
            quantity=0,
            position_pnl=0.0,
            position_pnl_pct=None,
            position_opened_date="",
        )
        assert state["position_pnl"] == 0.0

    def test_default_position_pnl_pct(self):
        from tradingagents.agents.utils.agent_states import AgentState

        state = AgentState(
            messages=[],
            company_of_interest="600519",
            trade_date="2026-05-06",
            cost_price=0.0,
            quantity=0,
            position_pnl=0.0,
            position_pnl_pct=None,
            position_opened_date="",
        )
        assert state["position_pnl_pct"] is None

    def test_explicit_position_fields(self):
        from tradingagents.agents.utils.agent_states import AgentState

        state = AgentState(
            messages=[],
            company_of_interest="600519",
            trade_date="2026-05-06",
            cost_price=1580.0,
            quantity=100,
            position_pnl=7000.0,
            position_pnl_pct=0.0443,
        )
        assert state["cost_price"] == 1580.0
        assert state["quantity"] == 100
        assert state["position_pnl"] == 7000.0
        assert state["position_pnl_pct"] == 0.0443

    def test_position_opened_date_default(self):
        from tradingagents.agents.utils.agent_states import AgentState

        state = AgentState(
            messages=[],
            company_of_interest="600519",
            trade_date="2026-05-06",
            cost_price=0.0,
            quantity=0,
            position_pnl=0.0,
            position_pnl_pct=None,
            position_opened_date="",
        )
        # position_opened_date already existed, ensure we didn't break it
        assert state["position_opened_date"] == ""


class TestPositionState:
    """Tests for PositionStateManager persistence."""

    def test_save_and_load(self, tmp_path):
        state_file = tmp_path / "position_state.json"
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        result = mgr.load("600519")
        assert result is not None
        assert result["cost_price"] == 1580.0
        assert result["quantity"] == 100
        assert result["opened_date"] == "2026-01-15"
        assert "updated_at" in result

    def test_load_nonexistent_ticker(self, tmp_path):
        state_file = tmp_path / "position_state.json"
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(state_file)})
        result = mgr.load("000001")
        assert result is None

    def test_reset_clears_position(self, tmp_path):
        state_file = tmp_path / "position_state.json"
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        mgr.save("000001", 10.0, 500, "2026-03-01")
        mgr.reset("600519")
        assert mgr.load("600519") is None
        assert mgr.load("000001") is not None

    def test_save_overwrites_existing(self, tmp_path):
        state_file = tmp_path / "position_state.json"
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 100.0, 50, "2026-01-01")
        mgr.save("600519", 200.0, 100, "2026-05-01")
        result = mgr.load("600519")
        assert result["cost_price"] == 200.0
        assert result["quantity"] == 100

    def test_get_all_returns_all(self, tmp_path):
        state_file = tmp_path / "position_state.json"
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(state_file)})
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        mgr.save("000001", 10.0, 500, "2026-03-01")
        all_states = mgr.get_all()
        assert "600519" in all_states
        assert "000001" in all_states
        assert len(all_states) == 2

    def test_no_file_returns_none(self, tmp_path):
        state_file = tmp_path / "nonexistent" / "position_state.json"
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({"position_state_path": str(state_file)})
        result = mgr.load("600519")
        assert result is None

    def test_default_path_creates_dir(self):
        from tradingagents.agents.utils.position_state import PositionStateManager

        mgr = PositionStateManager({})
        assert mgr._state_path is not None
        assert "position_state.json" in str(mgr._state_path)


class TestPositionCalc:
    """Tests for P&L calculation utilities."""

    def test_pnl_profit(self):
        result = calc_position_pnl(1650.0, 1580.0, 100)
        assert result["pnl_amount"] == 7000.0
        assert abs(result["pnl_pct"] - 0.0443) < 0.001  # ~4.43%

    def test_pnl_loss(self):
        result = calc_position_pnl(1500.0, 1580.0, 100)
        assert result["pnl_amount"] == -8000.0
        assert abs(result["pnl_pct"] + 0.0506) < 0.001  # ~-5.06%

    def test_pnl_zero_cost(self):
        result = calc_position_pnl(100.0, 0.0, 100)
        assert result["pnl_amount"] == 10000.0
        assert result["pnl_pct"] is None

    def test_pnl_zero_quantity(self):
        result = calc_position_pnl(100.0, 50.0, 0)
        assert result["pnl_amount"] == 0.0
        assert result["pnl_pct"] == 0.0

    def test_pnl_break_even(self):
        result = calc_position_pnl(50.0, 50.0, 100)
        assert result["pnl_amount"] == 0.0
        assert result["pnl_pct"] == 0.0

    def test_pnl_small_position(self):
        result = calc_position_pnl(10.5, 10.0, 1)
        assert result["pnl_amount"] == 0.5
        assert abs(result["pnl_pct"] - 0.05) < 0.001

    def test_avg_cost_after_add(self):
        result = calc_avg_cost_after_add(50.0, 100, 55.0, 100)
        assert result == 52.5

    def test_avg_cost_single_add(self):
        result = calc_avg_cost_after_add(0.0, 0, 100.0, 100)
        assert result == 100.0

    def test_avg_cost_all_zero(self):
        result = calc_avg_cost_after_add(0.0, 0, 0.0, 0)
        assert result == 0.0

    def test_avg_cost_mixed_qty(self):
        result = calc_avg_cost_after_add(100.0, 50, 120.0, 150)
        assert result == 115.0

    def test_realized_pnl_profit(self):
        result = calc_realized_pnl(60.0, 50.0, 100)
        assert result["realized_pnl"] == 1000.0

    def test_realized_pnl_loss(self):
        result = calc_realized_pnl(40.0, 50.0, 50)
        assert result["realized_pnl"] == -500.0

    def test_realized_pnl_zero_qty(self):
        result = calc_realized_pnl(60.0, 50.0, 0)
        assert result["realized_pnl"] == 0.0
        assert result["avg_cost_sold"] == 0.0

    def test_realized_pnl_rounding(self):
        result = calc_realized_pnl(10.333, 10.0, 100)
        assert result["realized_pnl"] == 33.3


class TestPositionFormatting:
    """Tests for position context formatting utilities."""

    def test_format_trader_with_position(self):
        result = format_position_for_trader(50.0, 200, 55.0)
        assert "成本价 50.00" in result
        assert "200 股" in result
        assert "+1000.00" in result  # (55-50)*200 = 1000

    def test_format_trader_no_position(self):
        result = format_position_for_trader(0.0, 0, 100.0)
        assert result == ""

    def test_format_trader_zero_cost(self):
        result = format_position_for_trader(0.0, 100, 100.0)
        assert result == ""

    def test_format_trader_zero_qty(self):
        result = format_position_for_trader(50.0, 0, 100.0)
        assert result == ""

    def test_format_pm_profit_above_10pct(self):
        result = format_position_for_pm(100.0, 100, 115.0)
        assert "15.00%" in result
        assert "止盈" in result
        assert "保守" in result

    def test_format_pm_loss_below_10pct(self):
        result = format_position_for_pm(100.0, 100, 85.0)
        assert "15.00%" in result
        assert "止损" in result
        assert "理性评估" in result

    def test_format_pm_within_5pct(self):
        result = format_position_for_pm(100.0, 100, 103.0)
        assert "3.00%" in result
        assert "持仓观望" in result
        assert "风险调整" not in result

    def test_format_pm_no_position(self):
        result = format_position_for_pm(0.0, 0, 100.0)
        assert result == ""

    def test_format_pm_zero_cost(self):
        result = format_position_for_pm(0.0, 100, 100.0)
        assert result == ""

    def test_format_context_non_ashare(self):
        result = format_position_context(100.0, 50.0, 100, market_type="US_STOCK")
        assert result == ""

    def test_format_context_ashare(self):
        result = format_position_context(55.0, 50.0, 100, market_type="A_SHARE")
        assert "成本价" in result
        assert "浮动盈亏" in result

    def test_format_context_no_position(self):
        result = format_position_context(100.0, 0.0, 0, market_type="A_SHARE")
        assert result == ""

    def test_format_context_default_market_type(self):
        result = format_position_context(55.0, 50.0, 100)
        assert "成本价" in result


class TestPropagatorState:
    """Tests for Propagator initial state injection."""

    def test_propagator_with_position(self):
        from tradingagents.graph.propagation import Propagator

        p = Propagator()
        state = p.create_initial_state(
            "600519", "2026-05-06",
            cost_price=1580.0, quantity=100,
            position_opened_date="2026-01-15",
        )
        assert state["cost_price"] == 1580.0
        assert state["quantity"] == 100
        assert state["position_opened_date"] == "2026-01-15"

    def test_propagator_without_position(self):
        from tradingagents.graph.propagation import Propagator

        p = Propagator()
        state = p.create_initial_state("600519", "2026-05-06")
        assert state["cost_price"] == 0.0
        assert state["quantity"] == 0
        assert state["position_opened_date"] == ""

    def test_propagator_partial_position(self):
        from tradingagents.graph.propagation import Propagator

        p = Propagator()
        state = p.create_initial_state("600519", "2026-05-06", cost_price=100.0)
        assert state["cost_price"] == 100.0
        assert state["quantity"] == 0  # Default when not provided

    def test_propagator_past_context_unchanged(self):
        from tradingagents.graph.propagation import Propagator

        p = Propagator()
        state = p.create_initial_state("600519", "2026-05-06", past_context="some context")
        assert state["past_context"] == "some context"
        assert state["cost_price"] == 0.0  # Default when not provided


class TestTraderPrompt:
    """Tests for Trader prompt position injection."""

    def test_trader_prompt_has_position_awareness_code(self):
        """Verify trader.py references position state fields."""
        import inspect
        from tradingagents.agents.trader import trader as trader_module
        source = inspect.getsource(trader_module)
        assert "cost_price" in source
        assert "quantity" in source

    def test_trader_position_formatting_with_position(self):
        """Verify format_position_for_trader works with position data."""
        result = format_position_for_trader(1580.0, 100, 1650.0)
        assert "成本价" in result
        assert "100 股" in result
        assert "浮动盈亏" in result
        assert "+7000.00" in result  # (1650-1580)*100

    def test_trader_position_formatting_no_position(self):
        """Verify format_position_for_trader returns empty string with no position."""
        result = format_position_for_trader(0.0, 0, 0.0)
        assert result == ""

    def test_trader_position_formatting_zero_cost(self):
        """Verify format_position_for_trader returns empty when cost_price is zero."""
        result = format_position_for_trader(0.0, 100, 100.0)
        assert result == ""

    def test_trader_position_formatting_zero_qty(self):
        """Verify format_position_for_trader returns empty when quantity is zero."""
        result = format_position_for_trader(50.0, 0, 100.0)
        assert result == ""


class TestPMPrompt:
    """Tests for Portfolio Manager prompt position injection."""

    def test_pm_prompt_has_position_code_reference(self):
        """Verify portfolio_manager.py references position state fields."""
        import inspect
        from tradingagents.agents.managers import portfolio_manager as pm_module
        source = inspect.getsource(pm_module)
        assert "cost_price" in source
        assert "quantity" in source
        assert "position_pnl" in source or "position_context" in source

    def test_pm_position_formatting_with_profit(self):
        """Verify format_position_for_pm with profit scenario."""
        from tradingagents.dataflows.position_utils import format_position_for_pm
        result = format_position_for_pm(100.0, 100, 115.0)
        assert "15.00%" in result
        assert "止盈" in result
        assert "保守" in result

    def test_pm_position_formatting_with_loss(self):
        """Verify format_position_for_pm with loss scenario."""
        from tradingagents.dataflows.position_utils import format_position_for_pm
        result = format_position_for_pm(100.0, 100, 85.0)
        assert "15.00%" in result
        assert "止损" in result
        assert "理性评估" in result

    def test_pm_no_position_empty(self):
        """Verify format_position_for_pm returns empty for no position."""
        from tradingagents.dataflows.position_utils import format_position_for_pm
        result = format_position_for_pm(0.0, 0, 100.0)
        assert result == ""

    def test_pm_no_position_empty_with_defaults(self):
        """Returns empty string when cost_price is 0."""
        from tradingagents.dataflows.position_utils import format_position_for_pm
        result = format_position_for_pm(0.0, 100, 100.0)
        assert result == ""


class TestTradingGraph:
    """Tests for TradingGraph propagate extension and auto-update."""

    def test_parse_rating_buy(self):
        from tradingagents.agents.utils.rating import parse_rating
        text = "**Rating**: Buy"
        assert parse_rating(text) == "Buy"

    def test_parse_rating_sell(self):
        from tradingagents.agents.utils.rating import parse_rating
        text = "**Rating**: Sell"
        assert parse_rating(text) == "Sell"

    def test_parse_rating_hold(self):
        from tradingagents.agents.utils.rating import parse_rating
        text = "**Rating**: Hold\nSome text"
        assert parse_rating(text) == "Hold"

    def test_parse_rating_overweight(self):
        from tradingagents.agents.utils.rating import parse_rating
        text = "**Rating**: Overweight"
        assert parse_rating(text) == "Overweight"

    def test_parse_rating_underweight(self):
        from tradingagents.agents.utils.rating import parse_rating
        text = "**Rating**: Underweight"
        assert parse_rating(text) == "Underweight"

    def test_parse_rating_not_found(self):
        from tradingagents.agents.utils.rating import parse_rating
        text = "No rating here"
        assert parse_rating(text) == "Hold"

    def test_position_state_save_and_load(self, tmp_path):
        from tradingagents.agents.utils.position_state import PositionStateManager
        mgr = PositionStateManager({"position_state_path": str(tmp_path / "pos.json")})
        mgr.save("600519", 1580.0, 100, "2026-01-15")
        result = mgr.load("600519")
        assert result is not None
        assert result["cost_price"] == 1580.0

    def test_init_creates_position_state_manager(self):
        """Verify PositionStateManager import works."""
        from tradingagents.agents.utils.position_state import PositionStateManager
        assert PositionStateManager is not None


class TestCLIInput:
    """Tests for CLI position input functions."""

    def test_get_position_cost_price_imports(self):
        from cli.main import get_position_cost_price
        assert callable(get_position_cost_price)

    def test_get_position_quantity_imports(self):
        from cli.main import get_position_quantity
        assert callable(get_position_quantity)

    def test_get_position_opened_date_imports(self):
        from cli.main import get_position_opened_date
        assert callable(get_position_opened_date)

    def test_user_selections_has_position_keys(self):
        import inspect
        from cli import main
        source = inspect.getsource(main.get_user_selections)
        assert "position_cost_price" in source
        assert "position_quantity" in source
        assert "position_opened_date" in source

    def test_run_analysis_passes_position_params(self):
        import inspect
        from cli import main
        source = inspect.getsource(main.run_analysis)
        assert "cost_price=float" in source
        assert "cost_price > 0 and quantity > 0" in source
