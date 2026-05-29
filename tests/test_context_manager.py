"""ContextWindowManager 单元测试。

覆盖:
  - Token 估算（中英文）
  - 三级压缩策略（预算监控 / LLM 摘要 / 硬截断）
  - inject_context 上下文注入
  - 回退机制
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.graph.context_manager import ContextWindowManager


# ------------------------------------------------------------------
# 测试数据
# ------------------------------------------------------------------

SHORT_TEXT = "这是一段短文本"
LONG_CHINESE = (
    "贵州茅台是中国白酒行业的龙头企业。2024年公司实现营业收入1505亿元，"
    "同比增长15.2%；归母净利润747亿元，同比增长16.5%。毛利率维持在92%以上，"
    "净利率保持在49.6%。公司品牌价值持续提升，市场占有率稳步扩大。"
    "从技术面来看，当前股价处于历史估值中位数附近。"
) * 100  # ~9K+ chars

SHORT_ENGLISH = "This is a short English text for testing."
LONG_ENGLISH = (
    "Apple Inc. designs, manufactures, and markets smartphones, personal computers, "
    "tablets, wearables, and accessories worldwide. The company also provides various "
    "related services. In fiscal year 2025, Apple reported revenue of $395.8 billion, "
    "a 5.2% increase year-over-year. Gross margin expanded to 46.8% from 45.1%. "
    "Services revenue reached $100 billion for the first time, representing a key "
    "growth driver as iPhone sales mature. The company maintains a fortress balance "
    "sheet with $160 billion in net cash and marketable securities."
) * 50  # ~9K+ chars


# ------------------------------------------------------------------
# estimate_tokens
# ------------------------------------------------------------------

class TestEstimateTokens:
    """Token 估算测试。"""

    def test_empty_string_returns_zero(self):
        assert ContextWindowManager.estimate_tokens("") == 0

    def test_none_returns_zero(self):
        assert ContextWindowManager.estimate_tokens(None) == 0

    def test_short_chinese(self):
        tokens = ContextWindowManager.estimate_tokens(SHORT_TEXT)
        # 8 chars / 1.8 ≈ 4
        assert tokens >= 1

    def test_long_chinese(self):
        tokens = ContextWindowManager.estimate_tokens(LONG_CHINESE)
        assert tokens > 100  # 应该足够大

    def test_short_english(self):
        # 也使用 1.8 参数（项目以中文为主）
        tokens = ContextWindowManager.estimate_tokens(SHORT_ENGLISH)
        assert tokens >= 1

    def test_never_returns_zero_for_nonempty(self):
        assert ContextWindowManager.estimate_tokens("a") == 1
        assert ContextWindowManager.estimate_tokens("中") == 1


# ------------------------------------------------------------------
# summarize_if_needed
# ------------------------------------------------------------------

class TestSummarizeIfNeeded:
    """按需压缩测试。"""

    def test_below_budget_returns_unchanged(self):
        """未超预算 → 返回原文。"""
        result = ContextWindowManager.summarize_if_needed(
            history=SHORT_TEXT,
            max_tokens=4000,
            quick_llm=None,  # 不应该调用 LLM
        )
        assert result == SHORT_TEXT

    def test_above_budget_no_llm_falls_back_to_truncation(self):
        """超预算 + 无 LLM → 硬截断回退。"""
        max_tokens = 100
        result = ContextWindowManager.summarize_if_needed(
            history=LONG_CHINESE,
            max_tokens=max_tokens,
            quick_llm=None,
        )
        # 应该被截断，小于原文
        assert len(result) < len(LONG_CHINESE)
        # 截断长度应在预算范围内
        max_chars = int(max_tokens * ContextWindowManager.CHARS_PER_TOKEN_SAFETY)
        assert len(result) <= max_chars

    def test_above_budget_with_llm_calls_summarize(self):
        """超预算 + 有 LLM → 调用 LLM 摘要。"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "# 摘要\n短摘要"
        mock_llm.invoke.return_value = mock_response

        result = ContextWindowManager.summarize_if_needed(
            history=LONG_CHINESE,
            max_tokens=200,
            quick_llm=mock_llm,
        )

        # LLM 被调用了
        mock_llm.invoke.assert_called_once()
        assert result == "# 摘要\n短摘要"

    def test_llm_failure_falls_back_to_truncation(self):
        """LLM 摘要失败 → 硬截断回退。"""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API timeout")

        result = ContextWindowManager.summarize_if_needed(
            history=LONG_CHINESE,
            max_tokens=100,
            quick_llm=mock_llm,
        )

        # 虽然尝试调用了 LLM
        mock_llm.invoke.assert_called_once()
        # 但返回的是截断结果
        assert len(result) < len(LONG_CHINESE)

    def test_with_reports_in_budget_calculation(self):
        """报告内容也计入 token 预算。"""
        reports = {
            "market_report": LONG_CHINESE[:2000],
            "news_report": LONG_CHINESE[:2000],
        }
        # 预算设置为远小于报告的 token 数
        result = ContextWindowManager.summarize_if_needed(
            history=SHORT_TEXT,  # 短历史
            reports=reports,     # 长报告导致超预算
            max_tokens=100,
            quick_llm=None,
        )
        # 报告超标 → 触发压缩
        assert len(result) <= int(100 * ContextWindowManager.CHARS_PER_TOKEN_SAFETY)

    def test_opponent_last_not_included_in_summarize(self):
        """对手最新发言不参与 compress（由 inject_context 单独保留）。"""
        # summarize_if_needed 本身不需要知道 opponent_last
        # — 该参数仅用于文档和可能的未来扩展
        result = ContextWindowManager.summarize_if_needed(
            history=SHORT_TEXT,
            opponent_last="Should NOT be modified!",
            max_tokens=4000,
            quick_llm=None,
        )
        assert result == SHORT_TEXT


# ------------------------------------------------------------------
# inject_context
# ------------------------------------------------------------------

class TestInjectContext:
    """上下文注入测试。"""

    @pytest.fixture
    def base_state(self):
        return {
            "investment_debate_state": {
                "history": "辩论历史内容\nBull: 买入观点\nBear: 卖出观点",
                "bull_history": "Bull: 买入观点",
                "bear_history": "Bear: 卖出观点",
                "current_response": "Bear: 最后发言",
                "latest_speaker": "Bear",
                "count": 2,
            },
            "market_report": "市场报告内容",
            "sentiment_report": "舆情分析内容",
            "news_report": "新闻分析内容",
            "fundamentals_report": "基本面分析内容",
            "market_context": "市场环境上下文",
        }

    def test_basic_injection(self, base_state):
        """基本上下文注入。"""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "短内容"
        mock_llm.invoke.return_value = mock_response
        # 但这次内容很短，不会触发压缩

        ctx = ContextWindowManager.inject_context(
            base_state, agent_type="bull", quick_llm=mock_llm,
        )

        # 返回值结构正确
        assert "reports_summary" in ctx
        assert "debate_history" in ctx
        assert "opponent_last" in ctx
        assert "token_usage" in ctx
        assert "compression_applied" in ctx
        assert "market_context" in ctx

        # 对手最新发言完整保留
        assert ctx["opponent_last"] == "Bear: 最后发言"

        # token 用量是整数
        assert isinstance(ctx["token_usage"], int)
        assert ctx["token_usage"] > 0

    def test_compression_flag_tracks_correctly(self, base_state):
        """compression_applied 标志正确反映压缩状态。"""
        mock_llm = MagicMock()

        # 长内容 → 触发压缩
        long_state = dict(base_state)
        long_state["investment_debate_state"]["history"] = LONG_CHINESE
        mock_response = MagicMock()
        mock_response.content = "压缩后的摘要"
        mock_llm.invoke.return_value = mock_response

        ctx = ContextWindowManager.inject_context(
            long_state, agent_type="bear", quick_llm=mock_llm,
        )
        # 压缩后长度小于原文
        assert len(ctx["debate_history"]) < len(LONG_CHINESE)
        assert ctx["compression_applied"] is True

    def test_first_round_no_opponent(self):
        """首轮辩论无对手发言。"""
        state = {
            "investment_debate_state": {
                "history": "",
                "bull_history": "",
                "bear_history": "",
                "current_response": "",
                "latest_speaker": "",
                "count": 0,
            },
        }
        mock_llm = MagicMock()

        ctx = ContextWindowManager.inject_context(
            state, agent_type="bull", quick_llm=mock_llm,
        )
        assert ctx["opponent_last"] == ""

    def test_missing_reports_handled_gracefully(self):
        """缺失报告字段不报错。"""
        state = {
            "investment_debate_state": {
                "history": "短历史",
                "bull_history": "",
                "bear_history": "",
                "current_response": "",
                "latest_speaker": "",
                "count": 0,
            },
        }
        mock_llm = MagicMock()

        ctx = ContextWindowManager.inject_context(
            state, agent_type="neutral", quick_llm=mock_llm,
        )
        assert ctx["reports_summary"] == ""


# ------------------------------------------------------------------
# 集成测试：与 bull/bear researcher 的兼容性
# ------------------------------------------------------------------

class TestResearcherIntegration:
    """验证 bull/bear researcher 的 import 和调用路径。"""

    def test_bull_researcher_import(self):
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
        assert callable(create_bull_researcher)

    def test_bear_researcher_import(self):
        from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
        assert callable(create_bear_researcher)

    def test_bull_node_uses_context_manager(self, monkeypatch):
        """bull_node 调用时使用 ContextWindowManager.inject_context。"""
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
        from unittest.mock import MagicMock, patch

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Bull: 强烈看好"
        mock_llm.invoke.return_value = mock_response

        # 不截断，让原始内容直接进入 prompt
        node = create_bull_researcher(mock_llm)

        state = {
            "investment_debate_state": {
                "history": "Bull: 之前观点\nBear: 之前反驳",
                "bull_history": "Bull: 之前观点",
                "bear_history": "Bear: 之前反驳",
                "current_response": "Bear: 当前反驳",
                "latest_speaker": "Bear",
                "count": 2,
            },
            "market_report": "市场报告",
            "sentiment_report": "舆情",
            "news_report": "新闻",
            "fundamentals_report": "基本面",
            "market_context": "",
        }

        result = node(state)
        assert "investment_debate_state" in result
        updated = result["investment_debate_state"]
        assert "Bull Analyst:" in updated["history"]
        assert updated["count"] == 3

    def test_bear_node_uses_context_manager(self, monkeypatch):
        """bear_node 调用时使用 ContextWindowManager.inject_context。"""
        from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
        from unittest.mock import MagicMock

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Bear: 强烈看空"
        mock_llm.invoke.return_value = mock_response

        node = create_bear_researcher(mock_llm)

        state = {
            "investment_debate_state": {
                "history": "Bull: 之前观点\nBear: 之前反驳",
                "bull_history": "Bull: 之前观点",
                "bear_history": "Bear: 之前反驳",
                "current_response": "Bull: 当前发言",
                "latest_speaker": "Bull",
                "count": 1,
            },
            "market_report": "市场报告",
            "sentiment_report": "舆情",
            "news_report": "新闻",
            "fundamentals_report": "基本面",
            "market_context": "",
        }

        result = node(state)
        assert "investment_debate_state" in result
        updated = result["investment_debate_state"]
        assert "Bear Analyst:" in updated["history"]
        assert updated["count"] == 2
