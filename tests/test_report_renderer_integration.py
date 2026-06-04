"""TDD RED: executor._extract_report must use ReportRenderer.render().

executor.py `_extract_report()` (line 299) currently assembles reports using
bare ``"\n\n".join(parts)``. It should call ``ReportRenderer.render(final_state, plan)``
instead, which wraps each analyst section in a consistent three-section format
(核心结论 → 关键数据 → 风险提示).

These tests fail during the RED phase because executor.py does NOT yet call
ReportRenderer. They will pass after the replacement is made.

Related:
    - tradingagents/graph/report_renderer.py::ReportRenderer.render()
    - tradingagents/graph/executor.py::GraphExecutor._extract_report()
"""

import pathlib

from tradingagents.graph.report_renderer import ReportRenderer

# ---------------------------------------------------------------------------
# FAILING — executor code patterns (RED: executor does NOT use ReportRenderer)
# ---------------------------------------------------------------------------


def test_executor_does_not_call_renderer_yet():
    """RED: executor.py source shows ReportRenderer.render() is NOT yet called.

    Read executor.py source directly (no import) to verify the renderer
    integration is missing. This assertion will fail RED because
    ``ReportRenderer.render`` is absent from executor.py.

    Once the fix is applied, ``ReportRenderer.render`` WILL appear in source
    and this test passes (GREEN).
    """
    source = pathlib.Path("tradingagents/graph/executor.py").read_text(encoding="utf-8")

    # 当前状态确认（用于开发诊断 — 这部分不会触发 fail）
    has_join = 'return "\\n\\n".join(parts) if parts else ""' in source

    # 核心断言：assert ReportRenderer.render 存在于源码中
    # 当前不存在 → assertion fails → RED phase
    assert "ReportRenderer.render" in source, (
        f"RED: executor.py lacks 'ReportRenderer.render'. "
        f"Current _extract_report (line 329) still uses: "
        f"return \"\\n\\n\".join(parts) if parts else \"\" "
        f"(present={has_join}). "
        f"Must replace with 'report = ReportRenderer.render(final_state, plan)'."
    )


def test_executor_report_lacks_core_sections():
    """RED: executor._extract_report output lacks three-section markers.

    Run ``_extract_report`` with realistic sample state and verify the
    output contains the structured ``**核心结论**`` / ``**关键数据**`` /
    ``**风险提示**`` wrappers that ReportRenderer provides.

    Currently _extract_report just concatenates raw LLM output without
    any section wrapping → this test FAILS.
    """
    from tradingagents.graph.executor import GraphExecutor

    sample_state = {
        "market_report": "市场走势良好，指数上涨。MACD金叉确认。成交量温和放大。",
        "fundamentals_report": "基本面稳健，PE为15倍，营收增长20%。负债率可控。",
        "sentiment_report": "舆情偏正面，机构评级买入。",
    }
    result = GraphExecutor._extract_report(sample_state)

    assert "**核心结论**" in result, (
        "RED: executor._extract_report output does not contain '**核心结论**'.\n"
        "Expected after replacing with ReportRenderer.render().\n"
        f"Actual output (first 200 chars):\n{result[:200]}"
    )
    assert "**关键数据**" in result, (
        "RED: executor._extract_report output does not contain '**关键数据**'."
    )
    assert "**风险提示**" in result, (
        "RED: executor._extract_report output does not contain '**风险提示**'."
    )


def test_executor_still_uses_raw_join():
    """RED: executor._extract_report uses ``\\n\\n.join()`` instead of ReportRenderer.

    Read executor.py source to assert that the raw join pattern is NO LONGER
    present. It IS still present at line 329 → assertion fails → RED.

    After the fix, ``ReportRenderer.render()`` replaces the join and this test passes.
    """
    source = pathlib.Path("tradingagents/graph/executor.py").read_text(encoding="utf-8")

    # Assert the raw join is GONE — currently it's present, so this FAILS
    assert 'return "\\n\\n".join(parts) if parts else ""' not in source, (
        "RED: executor.py _extract_report still uses '\"\\n\\n\".join(parts)'. "
        "Must be replaced with ReportRenderer.render(final_state, plan)."
    )


def test_executor_report_vs_renderer_diverge():
    """RED: executor and ReportRenderer produce DIFFERENT output for same input.

    Feed identical sample data to both ``_extract_report`` and
    ``ReportRenderer.render``. Currently they diverge because executor
    doesn't use the renderer. This test asserts they should match —
    it will FAIL now and PASS after replacement.
    """
    from tradingagents.graph.executor import GraphExecutor

    sample_state = {
        "market_report": "市场震荡上行，支撑位明确。",
        "fundamentals_report": "营收增长15%，毛利率稳定。",
        "investment_plan": "建议持有，目标价上调。",
    }
    plan = {"intent": "standard_analysis"}

    executor_output = GraphExecutor._extract_report(sample_state)
    renderer_output = ReportRenderer.render(sample_state, plan)

    # They should be the same (executor should delegate to renderer)
    assert executor_output == renderer_output, (
        f"RED: executor._extract_report and ReportRenderer.render produce "
        f"different outputs for the same input.\n"
        f"Executor output (first 150): {executor_output[:150]!r}\n"
        f"Renderer output (first 150): {renderer_output[:150]!r}\n"
        "Fix: replace _extract_report body with ReportRenderer.render(...)"
    )


# ---------------------------------------------------------------------------
# PASSING — ReportRenderer behavior (stable code from v0.2.16-cn)
# ---------------------------------------------------------------------------


def test_report_renderer_handles_empty_state():
    """ReportRenderer.render({}, None) returns '' without raising."""
    result = ReportRenderer.render({}, None)
    assert result == "", f"Expected empty string, got {result!r}"


def test_report_renderer_handles_str_input():
    """ReportRenderer.render_section accepts plain string without raising."""
    result = ReportRenderer.render_section("Test", "plain text")
    assert isinstance(result, str)
    assert len(result) > 0


def test_report_renderer_output_has_three_sections():
    """render_section output contains 核心结论, 关键数据, 风险提示."""
    result = ReportRenderer.render_section(
        "Test",
        "股票走势良好，MACD金叉确认。\n风险在于成交量不足。",
    )
    assert "**核心结论**" in result, "Missing 核心结论 in rendered output"
    assert "**关键数据**" in result, "Missing 关键数据 in rendered output"
    assert "**风险提示**" in result, "Missing 风险提示 in rendered output"
