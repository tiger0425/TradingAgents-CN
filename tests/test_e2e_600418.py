"""600418（江淮汽车）端到端回归测试。

验证：
  1. 行业检测：get_industry("600418") → "商用载货车"
  2. 行业注入 Context → Planner plan
  3. 最终分析结果不产生 AI/云服务幻觉
"""
import os
from typing import Any

import pytest

from tradingagents.dataflows.a_stock_data import get_industry


def test_get_industry_600418():
    """行业检测应返回包含"商用载货"的结果。"""
    result = get_industry("600418")
    assert result is not None
    assert "商用载货" in result or "载货" in result, (
        f"期望包含'商用载货车'，实际得到: {result}"
    )


@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="需要 DEEPSEEK_API_KEY 环境变量",
)
def test_industry_in_context():
    """行业信息应注入到 planner 的 context 中。"""
    from tradingagents.bootstrap import lazy_bootstrap
    from tradingagents.planner.schemas import Trigger, Context

    boot: Any = lazy_bootstrap()
    if boot is None:
        pytest.skip("bootstrap 失败，请检查 API key")
    planner, _executor, _kb, _pm = boot

    industry = get_industry("600418")
    assert "商用载货" in industry, f"行业检测失败: {industry}"

    trigger = Trigger(
        type="customer_message",
        message="分析600418",
        task="",
    )
    context = Context(
        user_id="test-600418",
        ticker="600418",
        industry=industry,
        portfolio_summary="",
    )
    plan = planner.plan(trigger, context)

    plan_str = str(plan)
    assert "600418" in plan_str, "Plan 应引用 600418"
    assert any(kw in plan_str for kw in ["商用", "载货", "江淮"]), (
        f"Plan 应包含行业或公司名称，当前 plan: {plan_str[:200]}"
    )


# 幻觉检测关键词
_HALLUCINATION_KWS = [
    "AI", "人工智能", "云服务", "大模型", "算力",
    "深度学习", "机器学习", "自然语言处理",
    "computer vision",
]


@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="需要 DEEPSEEK_API_KEY 环境变量",
)
def test_no_ai_hallucination():
    """完整管线：600418 分析不应产生 AI/算力幻觉。

    江淮汽车是商用车制造商，分析应围绕汽车/整车行业，而非 AI/科技。
    """
    from tradingagents.bootstrap import lazy_bootstrap
    from tradingagents.planner.schemas import Trigger, Context

    boot2: Any = lazy_bootstrap()
    if boot2 is None:
        pytest.skip("bootstrap 失败，请检查 API key")
    planner, executor, _kb, _pm = boot2

    industry = get_industry("600418")
    trigger = Trigger(
        type="customer_message",
        message="分析600418江淮汽车",
        task="",
    )
    context = Context(
        user_id="test-600418",
        ticker="600418",
        industry=industry,
        portfolio_summary="",
    )
    plan = planner.plan(trigger, context)
    result = executor.execute(plan, trigger, context)

    report = result.get("final_report", "") or ""
    plan_str = str(plan)

    found = [kw for kw in _HALLUCINATION_KWS
             if kw.lower() in report.lower() or kw.lower() in plan_str.lower()]
    assert len(found) == 0, (
        f"检测到幻觉！600418 分析中出现 AI/科技词汇: {found}"
    )

    # 应包含行业相关词汇
    assert any(term in report for term in ["车", "商用", "载货", "江淮", "整车", "汽车"]), (
        "报告应包含汽车/整车行业词汇"
    )
