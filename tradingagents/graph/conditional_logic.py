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
        # 工具调用限制（FIX-8）
        self.max_tool_calls_per_analyst = 12      # 每个分析师最多 12 次工具调用
        self.max_repeat_calls = 3                 # 同一工具+参数最多重复 3 次
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

        # --- 检查 1: 连续重复 ---
        last_calls: list[str] = []
        for msg in tool_call_msgs[-5:]:  # 最近 5 次带工具调用的消息
            for tc in msg.tool_calls:
                call_key = f"{tc.get('name', '')}:{str(tc.get('args', {}))}"
                last_calls.append(call_key)

        if last_calls:
            counter = Counter(last_calls)
            most_common = counter.most_common(1)[0]
            if most_common[1] >= self.max_repeat_calls:
                logger.warning(
                    "Tool loop detected for %s: %d repeat calls of '%s'",
                    analyst_type, most_common[1], most_common[0],
                )
                return True, "repeat_detected"

        # --- 检查 2: 总调用次数超限 ---
        tool_msg_count = sum(
            1 for msg in messages
            if hasattr(msg, 'tool_calls') and msg.tool_calls
        )
        if tool_msg_count >= self.max_tool_calls_per_analyst:
            logger.warning(
                "Tool call limit exceeded for %s: %d calls",
                analyst_type, tool_msg_count,
            )
            return True, "limit_exceeded"

        # --- 检查 3: 交替无进展 ---
        # 如果最近 6+ 次调用只有 2-3 种组合且严格交替 → 无进展
        if len(last_calls) >= 6:
            unique = set(last_calls)
            if 2 <= len(unique) <= 3:
                # 确认没有连续重复（连续重复已在检查 1 捕获）
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
            is_loop, reason = self._detect_tool_loop(state, "market")
            if is_loop:
                logger.warning("Breaking market analyst tool loop: %s", reason)
                self._inject_break_message(state, reason)
                if reason == "limit_exceeded":
                    return "Msg Clear Market"
                return "continue"
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            is_loop, reason = self._detect_tool_loop(state, "social")
            if is_loop:
                logger.warning("Breaking social analyst tool loop: %s", reason)
                self._inject_break_message(state, reason)
                if reason == "limit_exceeded":
                    return "Msg Clear Social"
                return "continue"
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            is_loop, reason = self._detect_tool_loop(state, "news")
            if is_loop:
                logger.warning("Breaking news analyst tool loop: %s", reason)
                self._inject_break_message(state, reason)
                if reason == "limit_exceeded":
                    return "Msg Clear News"
                return "continue"
            return "tools_news"
        return "Msg Clear News"

    def should_continue_fundamentals(self, state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            is_loop, reason = self._detect_tool_loop(state, "fundamentals")
            if is_loop:
                logger.warning("Breaking fundamentals analyst tool loop: %s", reason)
                self._inject_break_message(state, reason)
                if reason == "limit_exceeded":
                    return "Msg Clear Fundamentals"
                return "continue"
            return "tools_fundamentals"
        return "Msg Clear Fundamentals"

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_break_message(state: AgentState, reason: str) -> None:
        """向消息列表注入终止提示，指导 LLM 基于已获取数据生成报告。"""
        state["messages"].append(
            HumanMessage(content=(
                "工具调用已终止（原因：{reason}）。"
                "请基于已获取的数据生成你的分析报告。"
                "如果数据不足，请标注局限性并继续。"
            ).format(reason=reason))
        )

    # ------------------------------------------------------------------
    # FIX-2: 辩论路由枚举化（基于 latest_speaker，防死循环安全上限）
    # FIX-5: 集成辩论质量追踪 — 提前终止低质量辩论
    # ------------------------------------------------------------------
    def should_continue_debate(self, state: AgentState) -> str:
        """基于 latest_speaker 的枚举路由 + 质量驱动的提前终止。"""
        debate = state["investment_debate_state"]

        # 安全上限：防死循环（正常轮数 + 2 轮冗余）
        max_total = 2 * self.max_debate_rounds + 2
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
                    debate, self.max_debate_rounds
                )
                if decision == "terminate":
                    logger.info(
                        "Debate terminated early at round %d: quality degradation detected",
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
