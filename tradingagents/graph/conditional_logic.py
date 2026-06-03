# TradingAgents/graph/conditional_logic.py

import logging
from collections import Counter

from langchain_core.messages import HumanMessage

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph.debate_quality import DebateQualityTracker

logger = logging.getLogger(__name__)


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=2, max_risk_discuss_rounds=2):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds
        # 工具调用限制（FIX-8 — v0.2.11 收紧限制，根治死循环）
        self.max_tool_calls_per_analyst = 4        # 全局默认：每个分析师最多 4 次工具调用
        self.max_repeat_calls = 2                  # 同一工具+参数最多重复 2 次
        # 基本面具身定制：fundamentals analyst 已聚合三张表，2 工具即足够
        self._analyst_tool_limits: dict[str, int] = {
            "fundamentals": 3,
            "market": 8,
            "news": 5,
            "social": 5,
        }
        self._analyst_repeat_limits: dict[str, int] = {
            "market": 3,  # 4 tools, LLM may re-call same tool before moving on
        }
        # 辩论质量追踪器（FIX-5）
        self.quality_tracker = DebateQualityTracker()

    # ------------------------------------------------------------------
    # FIX-8: 工具调用死循环检测
    # ------------------------------------------------------------------
    def _detect_tool_loop(self, state: AgentState, analyst_type: str) -> tuple[bool, str]:
        """检测工具调用死循环。

        检查三种退化模式：
        1. 连续重复 — 同一工具+相同参数连续出现 >= max_repeat_calls 次
        2. 调用超限 — 历史总工具调用次数 >= max_tool_calls_per_analyst
        3. 交替无进展 — 最近 N 次调用仅由 2-3 种 (工具,参数) 组合构成，无新信息

        Returns:
            (True, reason) 如果检测到循环；(False, "ok") 如果正常。
        """
        messages = state["messages"]
        tool_call_msgs = [
            msg for msg in messages[-20:]  # 只看最近 20 条消息
            if hasattr(msg, 'tool_calls') and msg.tool_calls
        ]

        # --- 检查 1: 总调用次数超限（优先级最高）---
        tool_msg_count = sum(
            1 for msg in messages
            if hasattr(msg, 'tool_calls') and msg.tool_calls
        )
        max_allowed = self._analyst_tool_limits.get(
            analyst_type, self.max_tool_calls_per_analyst
        )
        if tool_msg_count >= max_allowed:
            logger.warning(
                "Tool call limit exceeded for %s: %d calls",
                analyst_type, tool_msg_count,
            )
            return True, "limit_exceeded"

        # --- 检查 2: 连续重复 ---
        last_calls: list[str] = []
        for msg in tool_call_msgs[-5:]:  # 最近 5 次带工具调用的消息
            for tc in msg.tool_calls:
                call_key = f"{tc.get('name', '')}:{str(tc.get('args', {}))}"
                last_calls.append(call_key)

        if last_calls:
            counter = Counter(last_calls)
            most_common = counter.most_common(1)[0]
            repeat_limit = self._analyst_repeat_limits.get(
                analyst_type, self.max_repeat_calls
            )
            if most_common[1] >= repeat_limit:
                logger.warning(
                    "Tool loop detected for %s: %d repeat calls of '%s'",
                    analyst_type, most_common[1], most_common[0],
                )
                return True, "repeat_detected"

        # --- 检查 3: 交替无进展 ---
        # 如果最近 6+ 次调用只有 2-3 种组合且严格交替 → 无进展
        if len(last_calls) >= 6:
            unique = set(last_calls)
            if 2 <= len(unique) <= 3:
                # 确认没有连续重复（连续重复已在检查 2 捕获）
                logger.warning(
                    "Tool loop detected for %s: alternating calls without progress "
                    "(unique=%d, total=%d)",
                    analyst_type, len(unique), len(last_calls),
                )
                return True, "alternating_no_progress"

        return False, "ok"

    # ------------------------------------------------------------------
    # 分析师条件路由（集成 FIX-8 死循环检测）
    # ------------------------------------------------------------------

    def should_continue_market(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            if ConditionalLogic._break_already_injected(messages):
                return "Msg Clear Market"
            if self._market_data_fully_fetched(messages):
                logger.info(
                    "Market: all data sources already retrieved, breaking tool loop"
                )
                self._inject_break_message(state, "all_data_retrieved", messages)
                return "tools_market"

            is_loop, reason = self._detect_tool_loop(state, "market")
            if is_loop:
                logger.warning("Breaking market analyst tool loop: %s", reason)
                self._inject_break_message(state, reason, messages)
                return "tools_market"
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            if ConditionalLogic._break_already_injected(messages):
                return "Msg Clear Social"
            if self._social_data_fully_fetched(messages):
                logger.info(
                    "Social: most data sources already retrieved, breaking tool loop"
                )
                self._inject_break_message(state, "all_data_retrieved", messages)
                return "tools_social"

            is_loop, reason = self._detect_tool_loop(state, "social")
            if is_loop:
                logger.warning("Breaking social analyst tool loop: %s", reason)
                self._inject_break_message(state, reason, messages)
                return "tools_social"
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            if ConditionalLogic._break_already_injected(messages):
                return "Msg Clear News"
            if self._news_data_fully_fetched(messages):
                logger.info(
                    "News: all data sources already retrieved, breaking tool loop"
                )
                self._inject_break_message(state, "all_data_retrieved", messages)
                return "tools_news"

            is_loop, reason = self._detect_tool_loop(state, "news")
            if is_loop:
                logger.warning("Breaking news analyst tool loop: %s", reason)
                self._inject_break_message(state, reason, messages)
                return "tools_news"
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            if ConditionalLogic._break_already_injected(messages):
                return "Msg Clear Fundamentals"
            if self._fundamentals_already_fetched(messages):
                logger.info(
                    "Fundamentals: get_fundamentals data already retrieved, breaking tool loop"
                )
                self._inject_break_message(state, "data_already_retrieved", messages)
                return "tools_fundamentals"

            is_loop, reason = self._detect_tool_loop(state, "fundamentals")
            if is_loop:
                logger.warning("Breaking fundamentals analyst tool loop: %s", reason)
                self._inject_break_message(state, reason, messages)
                return "tools_fundamentals"
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _fundamentals_already_fetched(messages) -> bool:
        """Check if get_fundamentals has been called 2+ times (i.e. LLM calling again).

        Allows the FIRST call to go through the ToolNode, then breaks the loop
        if the LLM attempts a second get_fundamentals call (since it already
        aggregates all financial statement data in one shot).
        """
        count = 0
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    if tc.get('name', '') == 'get_fundamentals':
                        count += 1
        return count >= 2

    @staticmethod
    def _break_already_injected(messages: list) -> bool:
        """Check if a break message was already injected in a prior cycle.

        If so, the ToolNode already did a no-op pass and the LLM was re-invoked.
        If the LLM still called tools (ignored the break message), force-clear
        to prevent infinite tools→break→tools→break recursion.
        """
        for m in messages[-3:]:
            txt = str(m.content) if hasattr(m, 'content') else ""
            if "工具调用已终止（原因：" in txt or "以下工具已经成功获取过数据" in txt:
                return True
        return False

    @staticmethod
    def _market_data_fully_fetched(messages) -> bool:
        """Check if most market data sources have been called.

        Market analyst tools: get_current_price, get_stock_data, get_indicators,
        get_market_context.  Breaking after 3+ unique tools are called prevents
        the LLM from chasing an unreachable 4th tool.
        """
        required = {"get_current_price", "get_stock_data", "get_indicators", "get_market_context"}
        called: set[str] = set()
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name', '')
                    if name in required:
                        called.add(name)
        return len(called) >= 3

    @staticmethod
    def _news_data_fully_fetched(messages) -> bool:
        """Check if both news tools have been called at least once."""
        required = {"get_news", "get_global_news"}
        called: set[str] = set()
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name', '')
                    if name in required:
                        called.add(name)
        return called == required

    @staticmethod
    def _social_data_fully_fetched(messages) -> bool:
        """Check if most social sentiment data sources have been called."""
        required = {"get_social_sentiment_tool", "get_news", "get_cls_flash", "get_hot_stock_reasons"}
        called: set[str] = set()
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    name = tc.get('name', '')
                    if name in required:
                        called.add(name)
        return len(called) >= 3

    @staticmethod
    def _inject_break_message(state: AgentState, reason: str, messages: list = None) -> None:
        """向消息列表注入终止提示，指导 LLM 基于已获取数据生成报告。

        _extract_repeated_tool_result 将工具返回的实际数据注入提示文本，
        防止 LLM 编造数字（如 DeepSeek 幻觉 ¥47.53）。
        """
        msg = (
            "工具调用已终止（原因：{reason}）。"
            "你必须立即基于已获取的数据生成分析报告。"
            "不要再调用任何工具。不要再请求更多数据。"
            "直接输出报告内容。如果数据确实不足，诚实标注局限性。"
        ).format(reason=reason)

        if messages:
            tool_data = ConditionalLogic._extract_repeated_tool_result(messages)
            if tool_data:
                msg = (
                    "以下工具已经成功获取过数据:\n\n"
                    + tool_data
                    + "\n\n" + msg
                )

        state["messages"].append(HumanMessage(content=msg))

    @staticmethod
    def _extract_repeated_tool_result(messages: list) -> str:
        """从消息历史中提取最近成功执行过的工具及其返回数据摘要。

        遍历消息，找到所有已完成（有 matching ToolMessage）的工具调用，
        返回简洁摘要供 LLM 参考，避免编造数据。
        """
        from langchain_core.messages import ToolMessage
        called: dict[str, str] = {}
        for i, m in enumerate(messages):
            if hasattr(m, 'tool_calls') and m.tool_calls:
                for tc in m.tool_calls:
                    name = tc.get('name', '')
                    if name not in called:
                        called[name] = "<结果未找到>"
                    # Look for matching ToolMessage
                    tc_id = tc.get('id', '')
                    for j in range(i + 1, len(messages)):
                        if (isinstance(messages[j], ToolMessage)
                                and getattr(messages[j], 'tool_call_id', '') == tc_id):
                            content = str(messages[j].content)
                            # Truncate long results to ~200 chars
                            if len(content) > 200:
                                content = content[:197] + "..."
                            called[name] = content
                            break
        lines = []
        for name, summary in sorted(called.items()):
            lines.append(f"- {name}: {summary}")
        return "\n".join(lines) if lines else ""

    # ------------------------------------------------------------------
    # FIX-2: 辩论路由枚举化（基于 latest_speaker，防死循环安全上限）
    # FIX-5: 集成辩论质量追踪 — 提前终止低质量辩论
    # ------------------------------------------------------------------
    def should_continue_debate(self, state: AgentState) -> str:
        """基于 latest_speaker 的枚举路由 + 质量驱动的提前终止 + 硬上限。"""
        debate = state["investment_debate_state"]

        # 安全上限：2*max_rounds + 1 缓冲（默认 max_debate_rounds=2 → 最多 5 轮）
        max_total = 2 * self.max_debate_rounds + 1
        if debate["count"] >= max_total:
            logger.warning(
                "Debate exceeded safety limit: %d rounds (max=%d)",
                debate["count"], max_total,
            )
            return "Research Manager"

        # --- FIX-5: 质量评估与提前终止 ---
        current_response = debate.get("current_response", "")
        count = debate.get("count", 0)
        if current_response and count > 0:
            # 每轮辩论后记录质量评分
            self.quality_tracker.evaluate_from_state(debate, current_response)

            # 完成正常轮数后开启质量检查（允许提前终止但不能增加轮数）
            if count >= 2 * self.max_debate_rounds:
                decision = self.quality_tracker.should_continue_with_quality(
                    debate, self.max_debate_rounds, min_quality_threshold=0.4
                )
                if decision == "terminate":
                    logger.info(
                        "Debate terminated early at round %d: quality degradation detected",
                        count,
                    )
                    return "Research Manager"
                # 硬上限：完成配置轮数+1 后强制终止（quality 未触发时生效）
                if count >= 2 * self.max_debate_rounds + 1:
                    logger.info(
                        "Debate reached hard cap at round %d (configured rounds exhausted)",
                        count,
                    )
                    return "Research Manager"

        # 枚举路由（与 risk debate 风格一致）
        speaker = debate.get("latest_speaker", "")
        if speaker == "Bull":
            return "Bear Researcher"
        elif speaker == "Bear":
            return "Bull Researcher"
        else:
            # Fallback: 首轮 latest_speaker 为空 → 从 Bull 开始
            return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """基于 latest_speaker 的枚举路由，替代脆弱的 startswith 字符串匹配。"""
        risk = state["risk_debate_state"]

        # 安全上限：防死循环（正常轮数 + 2 轮冗余）
        max_total = 3 * self.max_risk_discuss_rounds + 2
        if risk["count"] >= max_total:
            logger.warning(
                "Risk debate exceeded safety limit: %d rounds (max=%d)",
                risk["count"], max_total,
            )
            return "Portfolio Manager"

        # 枚举路由（精确匹配，不再依赖 LLM 输出的 startswith）
        speaker = risk.get("latest_speaker", "")
        if speaker == "Aggressive":
            return "Conservative Analyst"
        elif speaker == "Conservative":
            return "Neutral Analyst"
        elif speaker == "Neutral":
            return "Aggressive Analyst"
        else:
            # Fallback: 首轮 latest_speaker 为空 → 从 Aggressive 开始
            return "Aggressive Analyst"
