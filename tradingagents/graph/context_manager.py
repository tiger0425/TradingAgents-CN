"""上下文窗口管理器 — 三级策略管理 LLM Agent 的上下文注入。

策略层级:
  Level 1: Token 预算监控 — 实时追踪总 token 数
  Level 2: LLM 结构化摘要 — 超过预算时压缩而非截断
  Level 3: 硬截断 — LLM 调用失败时的最后防线

设计原则:
  - 中文 token 估算使用 len() // 1.8（而非 //4，后者严重低估中文 token 数）
  - 对手最新发言始终完整保留，不做压缩
  - 摘要格式结构化：保留具体数字、关键指标、核心论点、证据引用
  - 回退策略：LLM 摘要失败 → 硬截断（保留最近内容）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ContextWindowManager:
    """上下文窗口管理器。

    为 Layer 2 辩论 Agent 和 Layer 3 风控 Agent 提供统一的
    上下文压缩和注入服务，替代原来简陋的 "超 20 行就截断" 逻辑。

    用法::

        ctx_mgr = ContextWindowManager()
        context = ctx_mgr.inject_context(state, agent_type="bull", quick_llm=llm)
        prompt = build_prompt(
            reports=context["reports_summary"],
            debate_history=context["debate_history"],
            opponent=context["opponent_last"],
            ...
        )
    """

    # ---- Token 预算 ----
    DEBATE_TOKEN_BUDGET = 4000   # 辩论历史 + 报告 最大 token 数
    REPORT_TOKEN_BUDGET = 8000   # 分析师报告（单独使用时）最大 token 数

    # ---- 中文 token 估算参数 ----
    # 中文 ≈ 1.8 字符 / token（英文 ≈ 4 字符 / token）
    # 使用 1.8 而非 4，因为当前对话以中文为主
    CHINESE_TOKEN_RATIO = 1.8

    # ---- 硬截断安全系数 ----
    # 硬截断时保留的字符数 = max_tokens * CHARS_PER_TOKEN_SAFETY
    # 保守估计：中文 1 char ≈ 0.55 token
    CHARS_PER_TOKEN_SAFETY = 1.8

    # ---- 摘要约束 ----
    MAX_SUMMARY_CHARS_FACTOR = 4  # 摘要字符数上限 = max_tokens * factor

    def __init__(self) -> None:
        self._compression_applied: bool = False

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_tokens(text: Optional[str]) -> int:
        """估算文本的 token 数（中文友好）。

        使用 len() // 1.8 而非 //4，因为本项目对话以中文为主，
        中文约 1.5-2 字符/token，取 1.8 作为折中估算。

        Args:
            text: 待估算文本

        Returns:
            估算 token 数（整数）
        """
        if not text:
            return 0
        return max(1, int(len(text) / ContextWindowManager.CHINESE_TOKEN_RATIO))

    @classmethod
    def summarize_if_needed(
        cls,
        history: str,
        reports: Optional[Dict[str, str]] = None,
        max_tokens: int = DEBATE_TOKEN_BUDGET,
        quick_llm: Any = None,
        opponent_last: str = "",
    ) -> str:
        """按需压缩上下文：Token 预算 → LLM 摘要 → 硬截断回退。

        三级策略:
          1. Token 预算监控 — 未超预算则直接返回原文
          2. LLM 结构化摘要 — 超预算时调用 LLM 压缩
          3. 硬截断 — LLM 调用失败时的最后防线

        Args:
            history: 辩论历史文本（完整）
            reports: 分析师报告字典（key=报告名, value=内容），可选
            max_tokens: Token 预算上限
            quick_llm: LLM 客户端（需支持 .invoke()），为 None 时直接硬截断
            opponent_last: 对手最新发言（始终完整保留，已排除在压缩外）

        Returns:
            压缩后的历史文本（不超过 max_tokens 预算）
        """
        if reports is None:
            reports = {}

        # ---- Level 1: Token 预算监控 ----
        total_tokens = cls.estimate_tokens(history)
        for report_text in reports.values():
            total_tokens += cls.estimate_tokens(report_text)

        if total_tokens <= max_tokens:
            return history  # 无需压缩

        # ---- Level 2: LLM 结构化摘要 ----
        if quick_llm is not None:
            result = cls._llm_summarize(history, reports, max_tokens, quick_llm)
            if result is not None:
                # 二次校验：确保压缩后确实在预算内
                compressed_tokens = cls.estimate_tokens(result)
                logger.info(
                    "Context summarized: %d → %d tokens (budget: %d, ratio: %.1f%%)",
                    total_tokens, compressed_tokens, max_tokens,
                    (compressed_tokens / max_tokens) * 100,
                )
                return result

        # ---- Level 3: 硬截断回退 ----
        logger.warning(
            "Context summarization failed or no LLM available — "
            "falling back to hard truncation (budget: %d tokens, was: %d)",
            max_tokens, total_tokens,
        )
        max_chars = max_tokens * cls.CHARS_PER_TOKEN_SAFETY
        return history[-int(max_chars):]

    @classmethod
    def inject_context(
        cls,
        state: Dict[str, Any],
        agent_type: str,
        quick_llm: Any,
    ) -> Dict[str, Any]:
        """为指定 Agent 准备优化后的上下文。

        从 AgentState 中提取报告和历史，按需压缩后返回结构化上下文。

        Args:
            state: AgentState 字典（或兼容 dict-like 对象）
            agent_type: "bull" | "bear" | "aggressive" | "conservative" | "neutral"
            quick_llm: LLM 客户端（用于摘要生成）

        Returns:
            {
                "reports_summary": str,      # 可能已压缩的分析师报告文本
                "debate_history": str,        # 可能已压缩的辩论历史
                "opponent_last": str,         # 对手最新发言（始终完整保留）
                "token_usage": int,           # 估算总 token 数
                "compression_applied": bool,  # 是否触发了压缩
            }
        """
        # ---- 提取数据 ----
        debate = state.get("investment_debate_state", {})
        history = debate.get("history", "")
        opponent_last = debate.get("current_response", "")
        market_ctx = state.get("market_context", "")

        # 收集所有分析师报告
        reports: Dict[str, str] = {}
        for report_key in ("market_report", "sentiment_report", "news_report", "fundamentals_report"):
            report_val = state.get(report_key, "")
            if report_val:
                reports[report_key] = report_val

        # ---- 压缩处理 ----
        original_history = history
        compression_applied = False

        # 压缩历史（对手最新发言不参与压缩，后续单独追加）
        compressed_history = cls.summarize_if_needed(
            history=history,
            reports=reports,
            max_tokens=cls.DEBATE_TOKEN_BUDGET,
            quick_llm=quick_llm,
            opponent_last=opponent_last,
        )

        if compressed_history != original_history:
            compression_applied = True
            logger.debug(
                "Context compression applied for %s researcher (history: %d→%d chars)",
                agent_type, len(original_history), len(compressed_history),
            )

        # ---- 组装报告摘要 ----
        reports_text = cls._format_reports_summary(reports, cls.DEBATE_TOKEN_BUDGET, quick_llm)

        # ---- 计算 token 用量 ----
        token_usage = (
            cls.estimate_tokens(compressed_history)
            + cls.estimate_tokens(reports_text)
            + cls.estimate_tokens(opponent_last)
            + cls.estimate_tokens(market_ctx)
        )

        return {
            "reports_summary": reports_text,
            "debate_history": compressed_history,
            "opponent_last": opponent_last,
            "market_context": market_ctx,
            "token_usage": token_usage,
            "compression_applied": compression_applied,
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @classmethod
    def _llm_summarize(
        cls,
        history: str,
        reports: Dict[str, str],
        max_tokens: int,
        quick_llm: Any,
    ) -> Optional[str]:
        """调用 LLM 生成结构化摘要。

        Returns:
            摘要文本；如果 LLM 调用失败则返回 None（触发硬截断回退）
        """
        # 只对最近内容进行摘要（远历史不可丢弃）
        recent_history = history[-6000:] if len(history) > 6000 else history

        target_chars = max_tokens * 3  # 摘要目标长度（字符）

        summary_prompt = f"""将以下分析报告和辩论历史压缩为结构化摘要。
    保留：具体数字、关键指标、核心论点、证据引用。
    丢弃：重复表述、过度修饰、冗余分析。
    目标长度：不超过 {target_chars} 字符。

    报告:
    {cls._format_reports_text(reports)[:4000]}

    历史 （最近部分）:
    {recent_history}

    请输出严格按以下格式的结构化摘要:
    ## 分析师报告摘要
    - Market: [核心结论，1-2句]
    - Fundamentals: [核心结论，1-2句]
    - News: [核心结论，1-2句]
    - Social: [核心结论，1-2句]

    ## 辩论历史摘要
    - Bull [轮次1]: [核心论点 + 关键证据]
    - Bear [轮次1]: [核心论点 + 关键证据]
    - Bull [轮次2]: [核心论点 + 关键证据]
    - Bear [轮次2]: [核心论点 + 关键证据]
    """

        try:
            result = quick_llm.invoke(summary_prompt)
            content = result.content if hasattr(result, 'content') else str(result)

            # 防止 LLM 输出过长
            max_chars = int(max_tokens * cls.MAX_SUMMARY_CHARS_FACTOR)
            if len(content) > max_chars:
                logger.warning(
                    "LLM summary exceeded char limit (%d > %d), truncating",
                    len(content), max_chars,
                )
                content = content[:max_chars]

            return content
        except Exception as e:
            logger.warning("Context summarization failed: %s", e)
            return None

    @classmethod
    def _format_reports_text(cls, reports: Dict[str, str]) -> str:
        """将报告字典格式化为纯文本。"""
        lines = []
        for key, text in reports.items():
            if text:
                # 截断极长的报告
                display_text = text[:3000] if len(text) > 3000 else text
                lines.append(f"### {key}\n{display_text}")
        return "\n\n".join(lines)

    @classmethod
    def _format_reports_summary(
        cls,
        reports: Dict[str, str],
        max_tokens: int,
        quick_llm: Any = None,
    ) -> str:
        """格式化报告摘要：未超预算直接返回，超预算则 LLM 压缩。

        Args:
            reports: 报告字典
            max_tokens: 用于报告部分的 token 预算
            quick_llm: LLM 客户端（可选）

        Returns:
            格式化后的报告文本（可能已压缩）
        """
        reports_text = cls._format_reports_text(reports)
        reports_tokens = cls.estimate_tokens(reports_text)

        if reports_tokens <= max_tokens * 0.6:  # 报告占用预算的 60%
            return reports_text

        # 报告过长 → 单独压缩
        if quick_llm is not None:
            try:
                compact_prompt = f"""将以下分析师报告压缩为简短摘要（不超过 2000 字符）。

    {reports_text[:5000]}

    输出格式：
    - Market 报告: [核心结论]
    - Fundamentals 报告: [核心结论]
    - News 报告: [核心结论]
    - Social 报告: [核心结论]
    """
                result = quick_llm.invoke(compact_prompt)
                content = result.content if hasattr(result, 'content') else str(result)
                logger.info("Reports compressed: %d → %d chars", len(reports_text), len(content))
                return content
            except Exception as e:
                logger.warning("Reports summarization failed: %s — using truncated version", e)

        # 回退：直接截断报告
        max_chars = int(max_tokens * 0.6 * cls.CHARS_PER_TOKEN_SAFETY)
        return reports_text[:max_chars]

    @property
    def compression_applied(self) -> bool:
        """最近一次 inject_context() 是否触发了压缩。"""
        return self._compression_applied
