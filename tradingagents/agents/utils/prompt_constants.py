"""全局 prompt 常量 — 防幻觉、结构化输出约束

此文件仅依赖 config 模块，不导入任何业务 agent。
语言选择由 config.output_language 决定，不受 agent_type 影响。
"""

from tradingagents.dataflows.config import get_config


def get_anti_hallucination_instruction(
    agent_type: str = "analyst",
    lang: str = None,
) -> str:
    """全局防幻觉指令，按 agent 类型返回完整或轻量化约束。

    Args:
        agent_type: "analyst" 返回完整约束（6 条），
                    "debate" 返回轻量化约束（ADR 选项 B，4 条）。
        lang: 语言覆盖参数。为 None 时从 config.output_language 读取；
              非 None 时直接使用此值（兼容测试调用）。

    Returns:
        根据语言返回中文或英文约束字符串。
    """
    if lang is None:
        cfg = get_config()
        lang = cfg.get("output_language", "Chinese")

    # ── Debate Agent 轻量化约束（ADR 选项 B）─────────────────────
    if agent_type == "debate":
        if lang == "Chinese":
            return """
【防幻觉约束 — 辩论 Agent 轻量化版】

1. 只使用 bind_tools 列出的工具。
2. 数据缺失必须明确标注 — "[数据不可用]"，禁止编造。
3. 不要发明新数字，只引用分析师报告中的数据。
4. 报告语言：整篇报告必须用中文书写。
"""
        return """
【Anti-Hallucination Constraints — Debate Agent Light】

1. Only use tools listed in bind_tools.
2. If data is missing, state "[Data Unavailable]" — never fabricate.
3. Do not invent new numbers; only cite analyst reports.
4. Report language: write entire report in English.
"""

    # ── Analyst 完整约束 ───────────────────────────────────────
    if lang == "Chinese":
        return """
**【防幻觉约束 — 必须严格遵守】**

1. **只使用 bind_tools 列出的工具**。禁止调用未列出的工具名。
2. **数据缺失必须明确标注**。如果某项数据未获取到，写"[数据不可用]"而非编造。
3. **每个结论必须有工具输出引用**。在报告末尾的"数据来源"部分列出引用的工具名。
4. **不得编造财务指标**。所有数字必须来自 get_fundamentals、get_stock_data、get_indicators 等工具的真实输出。
5. **A 股分析禁止引用非中国市场的行业术语**。如出现 EPA 2027/Class 8/ACT Research 等美股/欧股术语，立即修正为 A 股对应概念。
6. **报告语言**：整篇报告必须用中文书写，禁止中英文混用。
"""
    return """
**【Anti-Hallucination Constraints — MANDATORY】**

1. Only use tools listed in bind_tools. Never invent tool names.
2. If data is missing, state "[Data Unavailable]" — never fabricate.
3. Every claim must reference specific tool output.
4. Never fabricate financial metrics. All numbers must come from tool outputs.
5. Do not inject non-target-market industry knowledge.
6. Report language: write entire report in English.
"""


def get_language_instruction() -> str:
    """返回输出语言指令。

    当 config.output_language 为 English 时返回空字符串（节省 token），
    否则返回写在该语言下的指令。用于面向用户的 agent（分析师、交易员、经理）。
    """
    lang = (get_config().get("output_language") or "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."
