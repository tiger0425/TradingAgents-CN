"""Extended tests for IndustryVerifier — benchmark detection & metric traceability.

TDD RED phase: these tests describe the desired interface and WILL FAIL
with AttributeError until the following methods are implemented on
IndustryVerifier:

    - verify_metric_sources(report, tool_messages) -> dict
    - detect_foreign_terms(report, market="A_SHARE") -> dict
    - detect_cross_report_contradictions(reports) -> dict
"""

import json

import pytest

from tradingagents.industry.verifier import IndustryVerifier


def test_industry_benchmark_unreferenced():
    """Report cites '行业平均 PE 50' but tool output lacks any PE data → warn.

    When the report claims a benchmark value that cannot be found in any
    tool-provided output, the verifier should flag it as a warning — the
    number may be hallucinated or sourced from an unknown reference.
    """
    report = (
        "根据行业分析，该公司的估值处于合理区间。"
        "行业平均 PE 50 倍，公司当前 PE 35 倍，低于行业平均水平。"
        "建议在估值低位逐步建仓。"
    )
    # Tool messages contain financial data but NO industry-average PE
    tool_messages = [
        {
            "role": "tool",
            "content": json.dumps({
                "financials": {"pe_ttm": 35.0, "revenue": 1e9},
                "industry_pe": None,
            }),
        },
        {
            "role": "tool",
            "content": json.dumps({
                "market_data": {"close": 15.5, "volume": 2e6},
            }),
        },
    ]

    result = IndustryVerifier.verify_metric_sources(report, tool_messages)

    assert result["verdict"] == "warn"
    assert len(result["issues"]) > 0
    # The issue should mention the unreferenced metric
    assert any("PE" in issue or "行业平均" in issue for issue in result["issues"])


def test_financial_metric_traced_to_tool_output():
    """Report says 'PE 30.5' and tool output contains 30.5 → pass.

    When every significant financial metric in the report can be found in
    the tool-call results, the metric-traceability check should pass.
    """
    report = (
        "贵州茅台最新财报显示 PE 30.5 倍，营收增长 15%。"
        "毛利率 91.5%，净利率 52%。配置建议：维持买入。"
    )
    tool_messages = [
        {
            "role": "tool",
            "content": json.dumps({
                "financials": {
                    "pe_ttm": 30.5,
                    "revenue_growth": 0.15,
                    "gross_margin": 0.915,
                    "net_margin": 0.52,
                },
            }),
        },
    ]

    result = IndustryVerifier.verify_metric_sources(report, tool_messages)

    assert result["verdict"] == "pass"
    assert len(result["issues"]) == 0


def test_financial_metric_not_in_tool_output():
    """Report says 'PE 25' but tool output lacks that value → warn.

    A financial metric appearing in the report that cannot be traced back
    to any tool-provided data should trigger a warning — the number may be
    hallucinated by the LLM.
    """
    report = (
        "根据计算，当前 PE 25 倍，处于历史低位。"
        "建议积极配置。"
    )
    tool_messages = [
        {
            "role": "tool",
            "content": json.dumps({
                "financials": {"pe_ttm": 30.5, "revenue_growth": 0.10},
            }),
        },
    ]

    result = IndustryVerifier.verify_metric_sources(report, tool_messages)

    assert result["verdict"] == "warn"
    assert len(result["issues"]) > 0
    assert any("PE" in issue or "25" in issue for issue in result["issues"])


def test_english_mode_hallucination_terms():
    """Report contains 'EPA 2027' (US-centric regulatory term) → fail.

    A-share analysis reports should not reference US regulatory bodies like
    the EPA. The presence of such English/US-centric terms indicates the LLM
    is hallucinating a foreign-market context and should be flagged as a
    hard failure.
    """
    report = (
        "EPA 2027 标准将于明年正式实施，预计增加公司排放处理成本"
        "约 2 亿元，对利润率产生负面影响。"
    )
    result = IndustryVerifier.detect_foreign_terms(report, market="A_SHARE")

    assert result["verdict"] == "fail"
    assert len(result["issues"]) > 0
    # The issue should reference the hallucinated term
    assert any("EPA" in issue for issue in result["issues"])


def test_cross_report_contradiction():
    """Market analyst says 'bullish' while fundamentals say 'bearish' → warn.

    When two reports (e.g. market-analysis vs. fundamentals) contain
    contradictory conclusions about the same instrument, the verifier
    should flag a cross-report contradiction.
    """
    reports = [
        {
            "agent": "market_analyst",
            "content": (
                "市场情绪高涨，资金持续北向流入，"
                "技术面 MACD 金叉，预计指数短期上行。"
                "强烈看涨。"
            ),
        },
        {
            "agent": "fundamentals_analyst",
            "content": (
                "公司基本面持续恶化，营收同比下滑 20%，"
                "负债率攀升至 75%，建议减仓回避。"
                "看跌。"
            ),
        },
    ]

    result = IndustryVerifier.detect_cross_report_contradictions(reports)

    assert result["verdict"] == "warn"
    assert len(result["issues"]) > 0
    # The issue should mention the contradiction
    assert any("矛盾" in issue or "contradiction" in issue.lower() or "看涨" in issue or "看跌" in issue for issue in result["issues"])
