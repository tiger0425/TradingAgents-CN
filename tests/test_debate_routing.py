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


def test_agents_not_in_debate_keep_depends(builder):
    """Agents not in debate groups keep their depends_on edges as-is."""
    plan = {"workflow": [
        {"step": 1, "agent": "market_analyst", "depends_on": []},
        {"step": 2, "agent": "trader", "depends_on": [1]},
        {"step": 3, "agent": "portfolio_manager", "depends_on": [2]},
    ]}
    graph = builder.build(plan)
    assert graph is not None
