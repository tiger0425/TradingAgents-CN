"""TDD RED: Verify bind_tools() lists match ToolNode registries.

Expected RED (failing) tests — bind_tools vs ToolNode mismatch:
  - test_fundamentals_bind_tools_match_toolnode: 1 tool vs 6
  - test_news_bind_tools_match_toolnode: 2 tools vs 3

Expected GREEN (passing) tests:
  - test_market_bind_tools_match_toolnode: 4 tools vs 4
  - test_social_bind_tools_match_toolnode: 4 tools vs 4
  - test_no_hallucinated_tool_calls: filter_valid_tool_calls strips bad calls
"""

import ast
import inspect

import pytest
from langchain_core.messages import AIMessage

from tradingagents.agents.analysts.fundamentals_analyst import (
    create_fundamentals_analyst,
)
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.social_media_analyst import (
    create_social_media_analyst,
)
from tradingagents.bootstrap import _create_tool_nodes
from tradingagents.agents.utils.agent_utils import filter_valid_tool_calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_tool_names(func) -> list[str]:
    """Parse source of factory function to extract tool names from ``tools = [...]``.

    Uses AST instead of calling the function (which would require heavy mocking
    of state/config arguments and trigger unwanted side effects).
    Returns a *sorted* list so the caller can compare semantically (set equality).
    """
    source = inspect.getsource(func)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "tools":
                    if isinstance(node.value, ast.List):
                        return sorted(
                            elt.id for elt in node.value.elts
                            if isinstance(elt, ast.Name)
                        )
    raise ValueError(f"Could not find 'tools = [...]' in {func.__name__}")


def _toolnode_names(key: str) -> list[str]:
    """Return sorted tool names from the bootstrap ToolNode for *key*."""
    tool_nodes = _create_tool_nodes()
    tn = tool_nodes[key]
    return sorted(tn.tools_by_name.keys())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_fundamentals_bind_tools_match_toolnode():
    """fundamentals_analyst tool list vs ToolNode — EXPECTED RED (1 vs 6)."""
    analyst_tools = _extract_tool_names(create_fundamentals_analyst)
    node_tools = _toolnode_names("fundamentals")
    assert analyst_tools == node_tools, (
        f"fundamentals_analyst bind_tools has {len(analyst_tools)} tool(s) "
        f"but ToolNode has {len(node_tools)}: "
        f"{analyst_tools} vs {node_tools}"
    )


@pytest.mark.unit
def test_news_bind_tools_match_toolnode():
    """news_analyst tool list vs ToolNode — EXPECTED RED (2 vs 3)."""
    analyst_tools = _extract_tool_names(create_news_analyst)
    node_tools = _toolnode_names("news")
    assert analyst_tools == node_tools, (
        f"news_analyst bind_tools has {len(analyst_tools)} tool(s) "
        f"but ToolNode has {len(node_tools)}: "
        f"{analyst_tools} vs {node_tools}"
    )


@pytest.mark.unit
def test_market_bind_tools_match_toolnode():
    """market_analyst tool list vs ToolNode — EXPECTED GREEN (4 vs 4)."""
    analyst_tools = _extract_tool_names(create_market_analyst)
    node_tools = _toolnode_names("market")
    assert analyst_tools == node_tools, (
        f"market_analyst bind_tools has {len(analyst_tools)} tool(s) "
        f"but ToolNode has {len(node_tools)}: "
        f"{analyst_tools} vs {node_tools}"
    )


@pytest.mark.unit
def test_social_bind_tools_match_toolnode():
    """social_media_analyst tool list vs ToolNode — EXPECTED GREEN (4 vs 4)."""
    analyst_tools = _extract_tool_names(create_social_media_analyst)
    node_tools = _toolnode_names("social")
    assert analyst_tools == node_tools, (
        f"social_media_analyst bind_tools has {len(analyst_tools)} tool(s) "
        f"but ToolNode has {len(node_tools)}: "
        f"{analyst_tools} vs {node_tools}"
    )


@pytest.mark.unit
def test_no_hallucinated_tool_calls():
    """filter_valid_tool_calls strips hallucinated tool calls not in valid_tools list."""
    # -- arrange: a FakeTool that quacks like a @tool-decorated function
    class FakeTool:
        def __init__(self, name: str):
            self.name = name

    valid_tools = [FakeTool("get_fundamentals")]

    result = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_fundamentals", "args": {}, "id": "call_1", "type": "tool_call"},
            {"name": "get_balance_sheet", "args": {}, "id": "call_2", "type": "tool_call"},
            {"name": "nonexistent_tool", "args": {}, "id": "call_3", "type": "tool_call"},
        ],
    )

    # -- act
    filter_valid_tool_calls(result, valid_tools)

    # -- assert
    # Only the valid tool remains
    assert len(result.tool_calls) == 1, (
        f"Expected 1 valid tool call, got {len(result.tool_calls)}"
    )
    assert result.tool_calls[0]["name"] == "get_fundamentals"

    # Hallucinated names are absent
    names = [tc["name"] for tc in result.tool_calls]
    assert "get_balance_sheet" not in names
    assert "nonexistent_tool" not in names

    # Feedback message was injected into content
    assert "已过滤不可用工具" in result.content, (
        "Expected Chinese feedback message in result.content after filtering"
    )
    for removed in ("get_balance_sheet", "nonexistent_tool"):
        assert removed in result.content, (
            f"Expected removed tool name '{removed}' in feedback message"
        )
    assert "get_fundamentals" in result.content, (
        "Expected remaining valid tool name in feedback message"
    )
