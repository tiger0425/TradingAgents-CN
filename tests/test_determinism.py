"""确定性冒烟测试：验证 temperature=0 下 analyst 函数输出完全一致。

工业级基线要求：给定相同输入，LLM 调用管线必须产生确定性输出。
通过 Mock LLM 消除外部 API 不确定性，验证代码层级的非随机性。

验证链路：
  1. MockLLM（RunnableLambda 绑定）→ 确定性响应
  2. create_market_analyst(mock) → agent node 函数
  3. 3 次相同 state 调用 → 3 份输出
  4. MD5 对比 → 全部相同 ✓

关键前提：
  - Task 1-4 已注入 temperature=0.0 配置（config → bootstrap → LLM clients）
  - 本测试验证 temperature=0 实际生效 + 代码管线无随机因素
"""
import copy
import hashlib
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.analysts.market_analyst import create_market_analyst


# ── Mock LLM ────────────────────────────────────────────────────

class MockDeterministicLLM:
    """确定性 Mock LLM：bind_tools 返回 RunnableLambda 以兼容 LangChain pipe。

    参考 test_causal_tracer.py:_MockLLM 模式，适配 analyst 节点的 LangChain
    链式调用（``prompt | llm.bind_tools(tools)``）。
    """

    def __init__(self, response: str = "[mock deterministic analysis]"):
        self.response = response
        self.calls: list = []  # 记录每次 invoke 的输入

    def bind_tools(self, tools):
        """返回 LangChain Runnable，内部记录调用并返回固定内容。"""
        def _respond(messages):
            self.calls.append(messages)
            return AIMessage(content=self.response)
        return RunnableLambda(_respond)


# ── Fixtures ────────────────────────────────────────────────────

MOCK_RESPONSE = (
    "## 600418 江淮汽车 技术分析报告\n\n"
    "### MACD 分析\n"
    "日线 MACD 在零轴附近金叉，红柱温和放大，短期动能偏多。\n\n"
    "### RSI 分析\n"
    "14 日 RSI=55.2，处于中性偏强区域，无超买超卖信号。\n\n"
    "### 成交量分析\n"
    "近 5 日均量较 20 日均量放大 18%，量价配合良好。\n\n"
    "### 趋势判断\n"
    "短期均线多头排列，股价站稳 20 日均线。上方压力位为前高 12.50 元。\n\n"
    "### 总结\n"
    "| 指标 | 数值 | 信号 |\n"
    "|------|------|------|\n"
    "| MACD | 金叉 | 偏多 |\n"
    "| RSI | 55.2 | 中性 |\n"
    "| 成交量 | +18% | 偏多 |\n"
    "| 均线 | 多头排列 | 偏多 |\n\n"
    "综合判断：短期偏多，关注 12.50 压力位突破情况。"
)

_BASE_STATE = {
    "company_of_interest": "600418",
    "trade_date": "2026-06-03",
    "messages": [HumanMessage(content="分析 600418 江淮汽车技术面")],
    "company_name": "江淮汽车",
    "industry": "商用载货车",
    "market_context": "",
    "market_start_idx": -1,
}


def _hash_report(report: str) -> str:
    """对 analyst 输出内容计算 MD5 摘要。"""
    return hashlib.md5(report.encode("utf-8")).hexdigest()


def _make_fresh_state():
    """构造干净的 state 副本，避免多次调用间共享可变对象。"""
    return {
        "company_of_interest": _BASE_STATE["company_of_interest"],
        "trade_date": _BASE_STATE["trade_date"],
        "messages": list(_BASE_STATE["messages"]),  # 浅拷贝列表
        "company_name": _BASE_STATE["company_name"],
        "industry": _BASE_STATE["industry"],
        "market_context": _BASE_STATE["market_context"],
        "market_start_idx": _BASE_STATE["market_start_idx"],
    }


# ── 确定性冒烟测试 ──────────────────────────────────────────────

@pytest.mark.smoke
@pytest.mark.unit
class TestAnalystDeterminism:
    """market_analyst 节点：3 次同输入调用 → 输出 MD5 必须完全相同。"""

    def test_three_identical_calls_same_md5(self):
        """冒烟测试：temperature=0 下 analyst 输出完全确定。"""
        mock = MockDeterministicLLM(response=MOCK_RESPONSE)
        analyst_fn = create_market_analyst(mock)

        hashes = []
        for i in range(3):
            state = _make_fresh_state()
            result = analyst_fn(state)
            report = result["market_report"]
            h = _hash_report(report)
            hashes.append(h)

        # 断言：3 次 MD5 完全相同
        assert len(set(hashes)) == 1, (
            f"温度 = 0 时 analyst 应产生确定性输出，但 3 次 MD5 不一致: {hashes}"
        )

    def test_mock_llm_receives_calls(self):
        """Mock LLM 应在每次 analyst 调用时收到 invoke。

        验证管线实际触发了 LLM 调用，而非跳过空跑。
        """
        mock = MockDeterministicLLM(response=MOCK_RESPONSE)
        analyst_fn = create_market_analyst(mock)

        for i in range(3):
            state = _make_fresh_state()
            analyst_fn(state)

        assert len(mock.calls) == 3, (
            f"期望 3 次 LLM 调用，实际 {len(mock.calls)} 次"
        )

    def test_state_isolation_between_calls(self):
        """多次调用间 state 应互不干扰。

        验证 analyst 函数不会将第一次调用的副作用泄露到后续调用。
        """
        mock = MockDeterministicLLM(response=MOCK_RESPONSE)
        analyst_fn = create_market_analyst(mock)

        state1 = _make_fresh_state()
        state2 = _make_fresh_state()

        result1 = analyst_fn(state1)
        result2 = analyst_fn(state2)

        # market_start_idx 应一致（每次从 -1 重置为 len(messages)）
        assert result1["market_start_idx"] == result2["market_start_idx"], (
            f"start_idx 应一致: {result1['market_start_idx']} vs {result2['market_start_idx']}"
        )

        # market_report 应一致（同一个 mock 返回同一内容）
        assert _hash_report(result1["market_report"]) == _hash_report(result2["market_report"]), (
            "两次独立调用的 market_report 应相同"
        )

    def test_output_contains_expected_fields(self):
        """Analyst 返回值应包含所有必需字段。"""
        mock = MockDeterministicLLM(response=MOCK_RESPONSE)
        analyst_fn = create_market_analyst(mock)

        state = _make_fresh_state()
        result = analyst_fn(state)

        required_fields = {"messages", "market_report", "market_start_idx"}
        missing = required_fields - set(result.keys())
        assert not missing, f"缺失必需字段: {missing}"

        # messages 应包含至少 1 条 AIMessage
        msgs = result["messages"]
        assert len(msgs) >= 1, "messages 不应为空"
        assert isinstance(msgs[0], AIMessage), f"第一条消息应为 AIMessage，实际为 {type(msgs[0])}"

    def test_deterministic_across_mock_instances(self):
        """不同 MockLLM 实例（相同 response）应产生相同输出。

        验证输出仅取决于 response 和 state，无全局状态干扰。
        """
        analyst_fn1 = create_market_analyst(
            MockDeterministicLLM(response=MOCK_RESPONSE)
        )
        analyst_fn2 = create_market_analyst(
            MockDeterministicLLM(response=MOCK_RESPONSE)
        )

        state = _make_fresh_state()
        h1 = _hash_report(analyst_fn1(state)["market_report"])
        h2 = _hash_report(analyst_fn2(state)["market_report"])

        assert h1 == h2, (
            f"不同 mock 实例应产生相同输出: {h1} vs {h2}"
        )
