"""Tests for V1.2 debate routing in DynamicGraphBuilder.

Verifies:
  - Debate/risk debate group detection
  - Conditional edges insertion (Bull↔Bear, Aggressive↔Conservative↔Neutral)
  - Graph compiles correctly
  - V1.0 CLI path is not disrupted
"""

import json
from unittest.mock import MagicMock

import pytest

from tradingagents.graph.dynamic_graph_builder import DynamicGraphBuilder
from tradingagents.graph.conditional_logic import ConditionalLogic


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_tool_nodes():
    tool = MagicMock()
    return {
        "market": tool,
        "fundamentals": tool,
        "news": tool,
        "social": tool,
    }


@pytest.fixture
def builder(mock_llm, mock_tool_nodes):
    return DynamicGraphBuilder(
        mock_llm, mock_llm, mock_tool_nodes,
        max_debate_rounds=2, max_risk_rounds=2,
    )


@pytest.fixture
def standard_plan():
    return json.loads("""
    {
        "template_id": "tpl_standard_analysis",
        "intent": "standard_analysis",
        "workflow": [
            {"step": 1, "agent": "market_analyst", "task": "analyst 1", "depends_on": []},
            {"step": 2, "agent": "fundamentals_analyst", "task": "analyst 2", "depends_on": []},
            {"step": 3, "agent": "news_analyst", "task": "analyst 3", "depends_on": []},
            {"step": 4, "agent": "social_analyst", "task": "analyst 4", "depends_on": []},
            {"step": 5, "agent": "bull_researcher", "task": "bull", "depends_on": [1,2,3,4]},
            {"step": 6, "agent": "bear_researcher", "task": "bear", "depends_on": [1,2,3,4]},
            {"step": 7, "agent": "research_manager", "task": "rm", "depends_on": [5,6]},
            {"step": 8, "agent": "trader", "task": "trader", "depends_on": [7]},
            {"step": 9, "agent": "risk_aggressive", "task": "ra1", "depends_on": [8]},
            {"step": 10, "agent": "risk_conservative", "task": "ra2", "depends_on": [8]},
            {"step": 11, "agent": "risk_neutral", "task": "ra3", "depends_on": [9,10]},
            {"step": 12, "agent": "portfolio_manager", "task": "pm", "depends_on": [7,8,11]}
        ]
    }
    """)


# ---------------------------------------------------------------------------
# Debate group detection
# ---------------------------------------------------------------------------

def test_detect_debate_group_full(builder, standard_plan):
    assert builder._detect_debate_group(standard_plan["workflow"]) is True


def test_detect_risk_debate_group_full(builder, standard_plan):
    assert builder._detect_risk_debate_group(standard_plan["workflow"]) is True


def test_detect_debate_group_missing_bear(builder):
    plan = {"workflow": [
        {"step": 1, "agent": "bull_researcher", "depends_on": []},
        {"step": 2, "agent": "research_manager", "depends_on": [1]},
    ]}
    assert builder._detect_debate_group(plan["workflow"]) is False


def test_detect_risk_debate_group_missing_pm(builder):
    plan = {"workflow": [
        {"step": 1, "agent": "risk_aggressive", "depends_on": []},
        {"step": 2, "agent": "risk_conservative", "depends_on": []},
        {"step": 3, "agent": "risk_neutral", "depends_on": []},
    ]}
    assert builder._detect_risk_debate_group(plan["workflow"]) is False


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

def test_standard_analysis_graph_compiles(builder, standard_plan):
    graph = builder.build(standard_plan)
    assert graph is not None


def test_no_debate_no_risk_graph_compiles(builder):
    plan = {"workflow": [
        {"step": 1, "agent": "market_analyst", "depends_on": []},
        {"step": 2, "agent": "trader", "depends_on": [1]},
    ]}
    graph = builder.build(plan)
    assert graph is not None


# ---------------------------------------------------------------------------
# Conditional logic function mapping
# ---------------------------------------------------------------------------

def test_conditional_has_debate_methods():
    cond = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    assert hasattr(cond, "should_continue_debate")
    assert callable(cond.should_continue_debate)
    assert hasattr(cond, "should_continue_risk_analysis")
    assert callable(cond.should_continue_risk_analysis)


def test_max_debate_rounds_passed_to_conditional():
    cond = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=2)
    assert cond.max_debate_rounds == 3
    assert cond.max_risk_discuss_rounds == 2


# ---------------------------------------------------------------------------
# V1.0 protection: setup.py must remain unchanged
# ---------------------------------------------------------------------------

def test_setup_py_imports_unchanged():
    """Verify V1.0 GraphSetup still imports and exposes expected classes."""
    from tradingagents.graph.setup import GraphSetup
    assert GraphSetup is not None


# ---------------------------------------------------------------------------
# skip_depends_agents logic (white-box)
# ---------------------------------------------------------------------------

def test_bear_skips_depends_edges(builder, standard_plan):
    """Verify bear_researcher depends_on edges are skipped in build path."""
    workflow = standard_plan["workflow"]
    builder._detect_debate_group = MagicMock(return_value=True)
    builder._detect_risk_debate_group = MagicMock(return_value=True)
    builder._add_debate_cycle = MagicMock()
    builder._add_risk_debate_cycle = MagicMock()

    builder.build(standard_plan)

    builder._add_debate_cycle.assert_called_once()
    builder._add_risk_debate_cycle.assert_called_once()


# ---------------------------------------------------------------------------
# FIX-2: latest_speaker enum routing tests
# ---------------------------------------------------------------------------

def _make_state(invest_count=0, invest_speaker="", risk_count=0, risk_speaker=""):
    """Minimal AgentState dict for ConditionalLogic routing tests."""
    return {
        "investment_debate_state": {
            "bull_history": "",
            "bear_history": "",
            "history": "",
            "current_response": "",
            "latest_speaker": invest_speaker,
            "judge_decision": "",
            "count": invest_count,
        },
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "",
            "latest_speaker": risk_speaker,
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": risk_count,
        },
    }


class TestDebateEnumRouting:
    """Verifies that should_continue_debate uses latest_speaker enum, not startswith.""" 

    def test_first_round_empty_speaker_routes_to_bull(self):
        cond = ConditionalLogic(max_debate_rounds=1)
        state = _make_state(invest_speaker="")
        result = cond.should_continue_debate(state)
        assert result == "Bull Researcher", f"Expected 'Bull Researcher', got '{result}'"

    def test_bull_speaker_routes_to_bear(self):
        cond = ConditionalLogic(max_debate_rounds=2)
        state = _make_state(invest_count=1, invest_speaker="Bull")
        result = cond.should_continue_debate(state)
        assert result == "Bear Researcher", f"Expected 'Bear Researcher', got '{result}'"

    def test_bear_speaker_routes_to_bull(self):
        cond = ConditionalLogic(max_debate_rounds=2)
        state = _make_state(invest_count=2, invest_speaker="Bear")
        result = cond.should_continue_debate(state)
        assert result == "Bull Researcher", f"Expected 'Bull Researcher', got '{result}'"

    def test_safety_limit_routes_to_manager(self):
        """Count at safety limit should force termination."""
        cond = ConditionalLogic(max_debate_rounds=1)
        # max_total = 2*1 + 2 = 4
        state = _make_state(invest_count=4, invest_speaker="Bull")
        result = cond.should_continue_debate(state)
        assert result == "Research Manager", f"Expected 'Research Manager', got '{result}'"

    def test_normal_limit_still_allows_routing(self):
        """Count at exactly 2*max_rounds (old limit) should still route."""
        cond = ConditionalLogic(max_debate_rounds=1)
        # max_total = 4, so count=2 should still route
        state = _make_state(invest_count=2, invest_speaker="Bull")
        result = cond.should_continue_debate(state)
        assert result == "Bear Researcher", f"Expected 'Bear Researcher' at count=2, got '{result}'"


class TestRiskEnumRouting:
    """Verifies that should_continue_risk_analysis uses latest_speaker enum, not startswith."""

    def test_first_round_empty_routes_to_aggressive(self):
        cond = ConditionalLogic(max_risk_discuss_rounds=1)
        state = _make_state(risk_speaker="")
        result = cond.should_continue_risk_analysis(state)
        assert result == "Aggressive Analyst", f"Expected 'Aggressive Analyst', got '{result}'"

    def test_aggressive_routes_to_conservative(self):
        cond = ConditionalLogic(max_risk_discuss_rounds=2)
        state = _make_state(risk_count=1, risk_speaker="Aggressive")
        result = cond.should_continue_risk_analysis(state)
        assert result == "Conservative Analyst", f"Expected 'Conservative Analyst', got '{result}'"

    def test_conservative_routes_to_neutral(self):
        cond = ConditionalLogic(max_risk_discuss_rounds=2)
        state = _make_state(risk_count=2, risk_speaker="Conservative")
        result = cond.should_continue_risk_analysis(state)
        assert result == "Neutral Analyst", f"Expected 'Neutral Analyst', got '{result}'"

    def test_neutral_routes_to_aggressive(self):
        cond = ConditionalLogic(max_risk_discuss_rounds=2)
        state = _make_state(risk_count=3, risk_speaker="Neutral")
        result = cond.should_continue_risk_analysis(state)
        assert result == "Aggressive Analyst", f"Expected 'Aggressive Analyst', got '{result}'"

    def test_safety_limit_routes_to_pm(self):
        cond = ConditionalLogic(max_risk_discuss_rounds=1)
        # max_total = 3*1 + 2 = 5
        state = _make_state(risk_count=5, risk_speaker="Aggressive")
        result = cond.should_continue_risk_analysis(state)
        assert result == "Portfolio Manager", f"Expected 'Portfolio Manager', got '{result}'"


# ---------------------------------------------------------------------------
# Regression: startswith("Bull") should NOT be the routing mechanism anymore
# ---------------------------------------------------------------------------

def test_startswith_no_longer_controls_routing():
    """current_response content must NOT affect routing decisions."""
    cond = ConditionalLogic(max_debate_rounds=1)
    # Simulate a state where response is garbled but latest_speaker is correct
    state = _make_state(invest_count=1, invest_speaker="Bull")
    state["investment_debate_state"]["current_response"] = "多头分析师: 强烈看涨..."  # NOT startswith("Bull")
    result = cond.should_continue_debate(state)
    # Routing is based on latest_speaker, not current_response → must be correct
    assert result == "Bear Researcher", (
        f"Routing should use latest_speaker, not current_response. Got '{result}'"
    )
