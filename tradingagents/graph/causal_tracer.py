"""因果追踪器 — 记录决策链上的每个关键节点。

追踪格式:
{
    "trace_id": "xxx",
    "timestamp": "2026-05-28T10:30:00",
    "final_decision": "Hold",
    "chain": [
        {
            "agent": "Market Analyst",
            "output_type": "report",
            "key_claim": "RSI=68, 接近超买区域",
        },
        {
            "agent": "Bear Researcher",
            "output_type": "argument",
            "round": 1,
            "claim": "估值 PE=35, 高于行业均值 22",
            "evidence": "PE 35 vs industry 22",
        },
        {
            "agent": "Research Manager",
            "output_type": "judgment",
            "decision": "Hold",
            "winning_side": "Bear",
            "basis": ["Bear's valuation concern is well-supported"],
        },
    ]
}
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 用于从文本中提取评级的关键词 ────────────────────────────────────
_RATING_ORDER = ["Buy", "Overweight", "Hold", "Underweight", "Sell"]
_RATING_PATTERN = re.compile(
    r"\b(Buy|Overweight|Hold|Underweight|Sell)\b", re.IGNORECASE
)


def _extract_rating(text: str) -> str:
    """从决策文本中提取评级（Buy/Overweight/Hold/Underweight/Sell）。

    优先返回评分最高的评级关键词。
    """
    found = _RATING_PATTERN.findall(text)
    if not found:
        return "Hold"
    for rating in _RATING_ORDER:
        if rating in found:
            return rating
    return "Hold"


def _extract_winning_side(text: str, polarity: str) -> str:
    """从文本中提取获胜方。

    polarity: "bull_bear" 或 "risk"
    """
    text_lower = text.lower()
    if polarity == "bull_bear":
        bull_score = text.count("bull") + text_lower.count("bullish")
        bear_score = text.count("bear") + text_lower.count("bearish")
        if bull_score > bear_score:
            return "Bull"
        elif bear_score > bull_score:
            return "Bear"
        return "Balanced"
    else:
        # risk debate: aggressive vs conservative vs neutral
        agg = text_lower.count("aggressive") + text_lower.count("risk-on")
        con = text_lower.count("conservative") + text_lower.count("risk-averse")
        neu = text_lower.count("neutral") + text_lower.count("balanced")
        winner = max(("Aggressive", agg), ("Conservative", con), ("Neutral", neu), key=lambda x: x[1])
        if winner[1] == 0:
            return "Balanced"
        return winner[0]


def _extract_basis(text: str, max_items: int = 5) -> List[str]:
    """从裁判决策文本中启发式提取关键依据项。

    按常见编号/分隔符拆分，取前 N 条。
    """
    basis = []
    lines = text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 跳过纯标题行、纯格式标记
        if line.startswith("#") or (line.startswith("*") and len(line) < 10):
            continue
        # 按句号分句（处理单行多句的情况）
        sub_sentences = re.split(r"[。.！!；;]", line)
        for sub in sub_sentences:
            sub = sub.strip()
            # 匹配常见列表格式
            cleaned = re.sub(r"^[\s]*[-•\*\d]+[\.\)、]\s*", "", sub)
            if len(cleaned) > 6 and cleaned not in basis:
                basis.append(cleaned[:200])
            if len(basis) >= max_items:
                break
        if len(basis) >= max_items:
            break

    return basis


class CausalTracer:
    """因果追踪器——记录决策链上的每个关键节点。

    在关键决策点记录 (决策, 依据, 来源) 三元组，
    最终输出 JSON 文件到 results_dir/{ticker}/traces/{date}.json。
    """

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.chain: List[Dict[str, Any]] = []

    # ── 记录方法 ──────────────────────────────────────────────────

    def record_analyst_report(
        self,
        agent: str,
        report: str,
        quick_llm=None,
    ) -> None:
        """从分析报告中提取核心主张。

        Args:
            agent: 分析师名称，如 "Market Analyst"
            report: 原始分析报告文本
            quick_llm: 轻量级 LLM 客户端（可选，用于提取关键发现）
        """
        key_claim = self._llm_extract(
            quick_llm,
            f"""从以下分析报告中提取最重要的一个核心发现（1-2句话）。
只返回发现本身，不要其他文字。

报告: {report[-1500:]}""",
            fallback=self._heuristic_extract_claim(report),
        )

        self.chain.append({
            "agent": agent,
            "output_type": "report",
            "key_claim": key_claim.strip() if key_claim else "[empty report]",
            "timestamp": datetime.now().isoformat(),
        })

    def record_debate_argument(
        self,
        agent: str,            # "Bull" | "Bear" | "Aggressive" | ...
        response: str,
        round_num: int,
        quick_llm=None,
    ) -> None:
        """记录辩论论点及其是否被后续裁判引用。

        Args:
            agent: 辩论方名称 (Bull/Bear/Aggressive/Conservative/Neutral)
            response: 辩论发言原文
            round_num: 辩论轮次 (1-based)
            quick_llm: 轻量级 LLM 客户端（可选）
        """
        fallback_claim = self._heuristic_extract_claim(response)
        # 尝试提取证据（数字+单位模式）
        fallback_evidence = self._heuristic_extract_evidence(response)

        try:
            if quick_llm:
                parsed = self._llm_extract_json(
                    quick_llm,
                    f"""从以下辩论发言中提取：
1. 核心论点（1句话）
2. 引用的具体证据（数字/数据）
只返回 JSON: {{"claim": "...", "evidence": "..."}}

发言: {response[-1000:]}""",
                )
            else:
                parsed = None
        except Exception:
            parsed = None

        claim = (parsed.get("claim") if parsed else None) or fallback_claim or "[extraction failed]"
        evidence = (parsed.get("evidence") if parsed else None) or fallback_evidence or ""

        self.chain.append({
            "agent": f"{agent} Researcher",
            "output_type": "argument",
            "round": round_num,
            "claim": claim,
            "evidence": evidence,
            "timestamp": datetime.now().isoformat(),
        })

    def record_judgment(
        self,
        agent: str,              # "Research Manager" | "Portfolio Manager"
        decision: str,
        winning_side: str,       # "Bull" | "Bear" | "Aggressive" | ...
        basis: Optional[List[str]] = None,
    ) -> None:
        """记录裁判决策。

        Args:
            agent: 裁判角色
            decision: 最终决策 (Buy/Overweight/Hold/Underweight/Sell)
            winning_side: 胜出方
            basis: 决策依据列表
        """
        self.chain.append({
            "agent": agent,
            "output_type": "judgment",
            "decision": decision,
            "winning_side": winning_side,
            "basis": basis or [],
            "timestamp": datetime.now().isoformat(),
        })

    def record_trader_plan(
        self,
        plan: str,
        quick_llm=None,
    ) -> None:
        """记录交易员的交易计划（作为特殊 report 类型）。"""
        key_claim = self._llm_extract(
            quick_llm,
            f"""从以下交易计划中提取最核心的操作建议（1-2句话）。
只返回建议本身，不要其他文字。

计划: {plan[-1500:]}""",
            fallback=self._heuristic_extract_claim(plan),
        )

        self.chain.append({
            "agent": "Trader",
            "output_type": "report",
            "key_claim": key_claim.strip() if key_claim else "[empty plan]",
            "timestamp": datetime.now().isoformat(),
        })

    # ── 输出方法 ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """输出完整追踪记录。"""
        return {
            "trace_id": self.trace_id,
            "final_decision": self._extract_final(),
            "chain": self.chain,
            "summary": self._generate_summary(),
            "generated_at": datetime.now().isoformat(),
        }

    def save(self, output_dir: Path, filename: str) -> str:
        """保存追踪记录为 JSON 文件。

        Args:
            output_dir: 输出目录
            filename: 文件名（不含扩展名）

        Returns:
            文件路径
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{filename}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info("Causal trace saved: %s (%d entries)", filepath, len(self.chain))
        return str(filepath)

    # ── 内部方法 ──────────────────────────────────────────────────

    def _extract_final(self) -> str:
        """从追踪链中提取最终决策。"""
        judgments = [
            e for e in self.chain
            if e.get("output_type") == "judgment"
        ]
        return judgments[-1]["decision"] if judgments else "unknown"

    def _generate_summary(self) -> str:
        """生成决策路径摘要。"""
        if not self.chain:
            return "Empty trace"

        steps = []
        for i, entry in enumerate(self.chain):
            agent = entry.get("agent", "Unknown")
            output_type = entry.get("output_type", "")

            if output_type == "report":
                claim = entry.get("key_claim", "")[:80]
                steps.append(f"{i+1}. {agent}: {claim}")
            elif output_type == "argument":
                round_num = entry.get("round", "?")
                claim = entry.get("claim", "")[:80]
                steps.append(f"{i+1}. {agent}(R{round_num}): {claim}")
            elif output_type == "judgment":
                decision = entry.get("decision", "?")
                winning_side = entry.get("winning_side", "?")
                steps.append(
                    f"{i+1}. ★ {agent}: **{decision}** "
                    f"(favors {winning_side})"
                )

        return "\n".join(steps)

    @staticmethod
    def _llm_extract(quick_llm, prompt: str, fallback: str = "") -> str:
        """安全调用 LLM 提取，失败返回 fallback。"""
        if quick_llm is None:
            return fallback
        try:
            result = quick_llm.invoke(prompt)
            content = result.content if hasattr(result, 'content') else str(result)
            return content.strip() if content else fallback
        except Exception as e:
            logger.warning("LLM extraction failed: %s", e)
            return "[extraction failed]"

    @staticmethod
    def _llm_extract_json(quick_llm, prompt: str) -> Optional[dict]:
        """安全调用 LLM 提取 JSON，失败返回 None。"""
        if quick_llm is None:
            return None
        try:
            result = quick_llm.invoke(prompt)
            content = result.content if hasattr(result, 'content') else str(result)
            # 提取 JSON 块
            json_match = re.search(r'\{[^{}]*\}', str(content))
            if json_match:
                return json.loads(json_match.group())
            return json.loads(content)
        except Exception as e:
            logger.warning("LLM JSON extraction failed: %s", e)
            return None

    @staticmethod
    def _heuristic_extract_claim(text: str) -> str:
        """启发式提取核心主张（不需要 LLM）。"""
        if not text.strip():
            return "[empty]"

        # 尝试找到 **本轮核心证据:** 部分
        evidence_match = re.search(
            r'\*\*本轮核心证据[：:]\s*\*\*\s*(.+?)(?:\n|$)',
            text, re.IGNORECASE,
        )
        if evidence_match:
            claim = evidence_match.group(1).strip()
            if len(claim) > 10:
                return claim[:200]

        # 尝试找到 **核心** 或 ### 开头的段落
        for pattern in [r'\*\*([^*]+)\*\*', r'###\s+(.+)']:
            matches = re.findall(pattern, text)
            for m in matches:
                stripped = m.strip()
                if len(stripped) > 10:
                    return stripped[:200]

        # 回退：取前120字符
        return text.strip()[:200]

    @staticmethod
    def _heuristic_extract_evidence(text: str) -> str:
        """启发式提取证据（数字+单位）。"""
        patterns = [
            r'(PE|P/E|市盈率)\s*[:：=]?\s*(\d+\.?\d*)',
            r'(ROE|净资产收益率)\s*[:：=]?\s*(\d+\.?\d*)%',
            r'(营收|收入|revenue)\s*(增长|增速|growth).*?(\d+\.?\d*)%',
            r'(\d+\.?\d*)%\s*(的|in)?\s*(营收|收入|利润|growth|revenue|profit)',
            r'(EPS|每股收益)\s*[:：=]?\s*(\d+\.?\d*)',
            r'(RSI).*?(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*倍',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = [g for g in match.groups() if g]
                return " ".join(groups)

        # 尝试任意数字+百分号
        pct_match = re.search(r'(\d+\.?\d*)%', text)
        if pct_match:
            return f"{pct_match.group(1)}%"

        return ""


def build_trace_from_state(
    tracer: CausalTracer,
    final_state: dict,
    quick_llm=None,
) -> None:
    """从 LangGraph final_state 构建完整追踪链。

    这是一个便利函数，应在 graph.invoke() 之后调用。
    所有 LLM 提取调用均已 wrapping try/except，不会阻断主流程。

    Args:
        tracer: CausalTracer 实例
        final_state: LangGraph graph.invoke() 的返回值
        quick_llm: 轻量级 LLM 客户端（可选）
    """
    if not final_state:
        return

    # 1. 记录分析师报告
    report_fields = [
        ("Market Analyst", "market_report"),
        ("Social Media Analyst", "sentiment_report"),
        ("News Analyst", "news_report"),
        ("Fundamentals Analyst", "fundamentals_report"),
    ]
    for agent_name, field in report_fields:
        report = final_state.get(field, "")
        if report:
            try:
                tracer.record_analyst_report(agent_name, report, quick_llm)
            except Exception as e:
                logger.warning("Tracer: failed to record %s report: %s", agent_name, e)

    # 2. 记录辩论论点（投资辩论）
    debate_state = final_state.get("investment_debate_state")
    if debate_state and isinstance(debate_state, dict):
        history = debate_state.get("history", "")
        if history:
            try:
                _extract_debate_arguments(tracer, history, quick_llm)
            except Exception as e:
                logger.warning("Tracer: failed to extract debate arguments: %s", e)

        # 3. 记录 Research Manager 裁判决策
        judge_decision = debate_state.get("judge_decision", "")
        if judge_decision:
            try:
                decision = _extract_rating(judge_decision)
                winning_side = _extract_winning_side(judge_decision, "bull_bear")
                basis = _extract_basis(judge_decision)
                tracer.record_judgment(
                    "Research Manager",
                    decision,
                    winning_side,
                    basis,
                )
            except Exception as e:
                logger.warning("Tracer: failed to record RM judgment: %s", e)

    # 4. 记录交易员计划
    trader_plan = final_state.get("trader_investment_plan", "")
    if trader_plan:
        try:
            tracer.record_trader_plan(trader_plan, quick_llm)
        except Exception as e:
            logger.warning("Tracer: failed to record trader plan: %s", e)

    # 5. 记录风险辩论
    risk_state = final_state.get("risk_debate_state")
    if risk_state and isinstance(risk_state, dict):
        history = risk_state.get("history", "")
        if history:
            try:
                _extract_risk_arguments(tracer, history, quick_llm)
            except Exception as e:
                logger.warning("Tracer: failed to extract risk arguments: %s", e)

        # 6. 记录 Portfolio Manager 裁判决策
        judge_decision = risk_state.get("judge_decision", "")
        if judge_decision:
            try:
                decision = _extract_rating(judge_decision)
                winning_side = _extract_winning_side(judge_decision, "risk")
                basis = _extract_basis(judge_decision)
                tracer.record_judgment(
                    "Portfolio Manager",
                    decision,
                    winning_side,
                    basis,
                )
            except Exception as e:
                logger.warning("Tracer: failed to record PM judgment: %s", e)


def _extract_debate_arguments(
    tracer: CausalTracer,
    history: str,
    quick_llm=None,
) -> None:
    """从投资辩论历史中提取各轮论点。"""
    # history 格式: "Bull Analyst: ...\nBear Analyst: ...\nBull Analyst: ..."
    # 按 "Bull Analyst:" 和 "Bear Analyst:" 分割
    entries = re.split(r'\n(?=Bull Analyst: |Bear Analyst: )', history.strip())
    round_num = 0
    bull_count = 0
    bear_count = 0

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        if entry.startswith("Bull Analyst:"):
            round_num = bull_count + 1
            bull_count += 1
            response = entry[len("Bull Analyst:"):].strip()
            agent = "Bull"
        elif entry.startswith("Bear Analyst:"):
            round_num = bear_count + 1
            bear_count += 1
            response = entry[len("Bear Analyst:"):].strip()
            agent = "Bear"
        else:
            continue

        if response:
            tracer.record_debate_argument(agent, response, round_num, quick_llm)


def _extract_risk_arguments(
    tracer: CausalTracer,
    history: str,
    quick_llm=None,
) -> None:
    """从风险辩论历史中提取各轮论点。"""
    # 各类发言前缀
    patterns = [
        ("Aggressive Analyst:", "Aggressive"),
        ("Conservative Analyst:", "Conservative"),
        ("Neutral Analyst:", "Neutral"),
    ]

    entries = re.split(r'\n(?=(?:Aggressive|Conservative|Neutral) Analyst: )', history.strip())
    counters = {"Aggressive": 0, "Conservative": 0, "Neutral": 0}

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        matched = False
        agent_type = ""
        round_num = 0
        response = ""
        for prefix, atype in patterns:
            if entry.startswith(prefix):
                counters[atype] += 1
                round_num = counters[atype]
                response = entry[len(prefix):].strip()
                agent_type = atype
                matched = True
                break

        if matched and response:
            tracer.record_debate_argument(agent_type, response, round_num, quick_llm)
