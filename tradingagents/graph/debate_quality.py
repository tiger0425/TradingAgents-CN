"""辩论质量追踪器 — 检测冗余、新证据、观点变化。

在每次辩论轮次结束时评估质量，支持基于质量的提前终止机制。

用法::

    tracker = DebateQualityTracker()
    score = tracker.evaluate_round(response, opponent_history, round_number)
    # 在 conditional_logic 中:
    if not tracker.should_continue(debate_state, max_rounds):
        return "Research Manager"   # 提前终止
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tradingagents.agents.utils.agent_states import AgentState
    from tradingagents.agents.utils.agent_states import InvestDebateState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 文本分析工具
# ---------------------------------------------------------------------------

def _extract_numbers(text: str) -> int:
    """提取文本中的数值型数据点数量。

    匹配：百分比、金额、倍数、带单位的数字、日期等。
    """
    patterns = [
        r"\d+(?:\.\d+)?%",                          # 百分比
        r"\$\d[\d,.]*(?:\s*(?:billion|million|万|亿))?",  # 金额
        r"\d+(?:\.\d+)?x",                           # 倍数
        r"\d+(?:\.\d+)?\s*(?:元|CNY|USD|RMB)",       # 带货币单位的数字
        r"\b\d+(?:\.\d+)?\s*(?:倍|个百分点)",           # 中文倍数/百分点
        r"(?:同比|环比|增长|下降|减少|增加)\s*\d+(?:\.\d+)?%",  # 变化率
        r"(?:PE|PB|ROE|ROA|毛利率|净利率)\s*[：:]*\s*\d+(?:\.\d+)?%?",  # 财务指标
        r"\b\d{2,4}(?:年|Q[1-4])",                   # 年份/季度
    ]
    total = 0
    for pat in patterns:
        total += len(re.findall(pat, text))
    return total


def _tokenize(text: str) -> set[str]:
    """将文本分词为有意义的 token 集合（去重）。"""
    # 提取中英文词、数字
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}|\d+(?:\.\d+)?%?", text.lower())
    return set(tokens)


def _compute_novelty(text: str, history_texts: list[str]) -> tuple[float, set[str]]:
    """计算文本相对于历史的新颖度分数和新增 tokens。

    Returns:
        (novelty_score, new_tokens) — novelty_score 范围 0.0-1.0
    """
    current_tokens = _tokenize(text)
    if not current_tokens:
        return 0.0, set()

    # 合并所有历史 tokens
    history_tokens: set[str] = set()
    for h in history_texts:
        history_tokens |= _tokenize(h)

    new_tokens = current_tokens - history_tokens
    novelty = len(new_tokens) / len(current_tokens) if current_tokens else 0.0
    return novelty, new_tokens


def _detect_opponent_addressing(text: str) -> float:
    """检测是否回应了对手的论点。

    返回 0.0-1.0 的得分：1.0 表示明确回应了多个对手论点。
    """
    addressing_patterns = [
        # 英文模式
        r"\byou (?:mentioned|said|noted|pointed|argued|claimed|asserted)\b",
        r"\byour (?:point|argument|claim|concern|analysis)\b",
        r"\bthe (?:bull|bear) (?:argues?|claims?|asserts?|contends?)\b",
        r"\b(?:however|but|while|although)\s+(?:the|you)\b",
        r"\bon the (?:bull|bear)\s*(?:side|argument|point)",
        r"\b(?:counter|refute|rebut|challenge)\b",
        r"\b(?:I\s+)?(?:disagree|agree|concede|acknowledge)\b",
        # 中文模式
        r"(?:多头|空头|对方|你)\s*(?:提到|指出|认为|主张|声称|说)",
        r"(?:反驳|质疑|回应|不同意)(?:对方|多头|空头|你)",
        r"(?:你方|对方)的\s*(?:论点|观点|数据|分析)",
        r"(?:承认|认同|部分同意)(?:对方|多头|空头|你)",
    ]
    match_count = 0
    for pat in addressing_patterns:
        matches = re.findall(pat, text, re.IGNORECASE)
        match_count += len(matches)

    # 归一化：0-2 次 → 0.3, 3-5 次 → 0.6, 6+ → 1.0
    if match_count >= 6:
        return 1.0
    elif match_count >= 3:
        return 0.6
    elif match_count >= 1:
        return 0.3
    return 0.0


def _detect_convergence(rounds: list[dict]) -> float:
    """检测最近 2 轮中是否出现观点收敛。

    如果双方都提到"同意"或"部分同意" → 高收敛分；
    辩论可能已经到达可决策点。
    """
    if len(rounds) < 2:
        return 0.0
    convergence_phrases = [
        r"\bagree\b", r"\bconcede\b", r"\backnowledge\b",
        r"\bcommon ground\b", r"\bconverge",
        r"同意", r"认同", r"部分同意", r"确有", r"不否认",
    ]
    converge_count = 0
    for rd in rounds[-2:]:
        text = rd.get("response", "")
        for pat in convergence_phrases:
            if re.search(pat, text, re.IGNORECASE):
                converge_count += 1
                break
    # 0 = no convergence, 0.5 = one shows, 1.0 = both show
    return min(converge_count / 2, 1.0)


# ---------------------------------------------------------------------------
# DebateQualityTracker
# ---------------------------------------------------------------------------

class DebateQualityTracker:
    """辩论质量追踪器。

    在每次辩论轮次结束时评估：
    1. 新证据检测 — 本轮是否引入了新数据/新论点
    2. 冗余检测 — 是否只是换措辞重复首轮内容
    3. 观点变化追踪 — Agent 是否在收到对手论点后调整了立场

    用于 conditional_logic 中的提前终止判断。
    """

    def __init__(self):
        self._round_scores: list[dict] = []  # 每轮评分记录

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    @staticmethod
    def detect_novel_evidence(
        current: str, history: list[str]
    ) -> tuple[bool, str]:
        """检测本轮是否引入了前轮未出现的新证据。

        不使用 LLM，使用轻量文本相似度分析：
        - 提取数值型数据点（百分比、金额、财务指标等）并比较
        - Token 级新颖度计算

        Args:
            current: 当前轮次的发言文本。
            history: 之前所有轮次的发言文本列表（不含当前轮）。

        Returns:
            (has_novel, evidence_summary)：
            - has_novel — 是否检测到显著新证据
            - evidence_summary — 简要说明（英文简述）
        """
        # 数值型数据点比较
        current_numbers = _extract_numbers(current)
        history_text = " ".join(history) if history else ""
        history_numbers = _extract_numbers(history_text)

        # Token 新颖度
        novelty_score, new_tokens = _compute_novelty(current, history)

        has_novel = False
        summary = "no new evidence"

        # 判定标准：数值增长 > 0 或新颖度 > 0.4
        if current_numbers > history_numbers and (current_numbers - history_numbers) >= 1:
            has_novel = True
            summary = f"+{current_numbers - history_numbers} new data points"
        elif novelty_score >= 0.4:
            has_novel = True
            sample_tokens = sorted(new_tokens)[:5]
            summary = f"new concepts: {', '.join(sample_tokens)}"

        # 如果没有历史（首轮），总是认为有新证据
        if not history:
            has_novel = True
            summary = "opening round: initial evidence"

        return has_novel, summary

    @staticmethod
    def compute_round_score(
        response: str,
        opponent_history: list[str],
        round_number: int,
    ) -> dict:
        """计算单轮辩论质量评分。

        Args:
            response: 本轮发言文本。
            opponent_history: 对手方所有历史发言。
            round_number: 当前轮次编号（从 1 开始）。

        Returns:
            {
                "novel_evidence": bool,       # 是否引入新证据
                "novelty_score": float,        # 新颖度分数 0.0-1.0
                "addressed_opponent": float,   # 回应对手程度 0.0-1.0
                "specific_claims": int,        # 包含多少具体数据点
                "overall_score": float,        # 综合质量分 0.0-1.0
                "evidence_summary": str,       # 证据简述
            }
        """
        # 1. 新证据检测
        has_novel, novel_summary = DebateQualityTracker.detect_novel_evidence(
            response, opponent_history
        )

        # 2. 新颖度计算（更细粒度的连续分数）
        novelty, _ = _compute_novelty(response, opponent_history)
        # 前两轮默认有较高新颖度（因为首次出现就有很多新信息）
        if round_number <= 2:
            novelty = max(novelty, 0.5)

        # 3. 对手回应检测
        addressed = _detect_opponent_addressing(response)
        # 首轮无对手论点可回应 → 给高分（基于初始分析质量）
        if not opponent_history or round_number == 1:
            addressed = 0.7  # 默认得分（初始分析本身有质量）

        # 4. 具体数据点数量
        specific_claims = _extract_numbers(response)

        # 5. 综合得分
        # 权重: 新颖度 30%, 回应对手 25%, 数据密度 25%, 证据存在 20%
        # 数据密度归一化：0个=0, 1-2个=0.4, 3-5个=0.7, 6+=1.0
        if specific_claims >= 6:
            density_score = 1.0
        elif specific_claims >= 3:
            density_score = 0.7
        elif specific_claims >= 1:
            density_score = 0.4
        else:
            density_score = 0.1

        overall = (
            novelty * 0.30
            + addressed * 0.25
            + density_score * 0.25
            + (1.0 if has_novel else 0.0) * 0.20
        )

        return {
            "novel_evidence": has_novel,
            "novelty_score": round(novelty, 3),
            "addressed_opponent": round(addressed, 3),
            "specific_claims": specific_claims,
            "overall_score": round(overall, 3),
            "evidence_summary": novel_summary,
        }

    def evaluate_round(
        self,
        response: str,
        opponent_history: list[str],
        round_number: int,
    ) -> dict:
        """评估一轮辩论质量并记录。

        Args:
            response: 本轮发言文本。
            opponent_history: 对手方历史发言文本列表。
            round_number: 当前轮次编号。

        Returns:
            评分字典（同 compute_round_score）。
        """
        score = self.compute_round_score(response, opponent_history, round_number)
        self._round_scores.append({
            "round": round_number,
            "response": response,  # 保存原始响应文本用于收敛检测
            **score,
        })
        logger.debug(
            "Round %d quality: %.3f (novelty=%.3f, addressed=%.3f, claims=%d)",
            round_number, score["overall_score"],
            score["novelty_score"], score["addressed_opponent"],
            score["specific_claims"],
        )
        return score

    def should_continue_with_quality(
        self,
        state: dict,
        max_rounds: int,
        min_quality_threshold: float = 0.3,
    ) -> str:
        """基于质量判断是否继续辩论。

        如果连续 2 轮质量评分 < min_quality_threshold（说明辩论已经枯竭），
        返回 "terminate"。也检测观点收敛。

        注意：此方法只检查质量相关终止条件，不强制 count 上限。
        count 上限由 should_continue_debate 的安全上限处理。

        Args:
            state: invest_debate_state 字典。
            max_rounds: 最大辩论轮数（保留用于未来扩展）。
            min_quality_threshold: 最低质量阈值（默认 0.3）。

        Returns:
            "continue" 或 "terminate"。
        """
        count = state.get("count", 0)

        # 至少需要 2 轮（Bull→Bear 各一次）才有质量数据来做决策
        if len(self._round_scores) < 2:
            return "continue"

        # 连续 2 轮低质量检查
        recent = self._round_scores[-2:]
        low_quality_count = sum(
            1 for s in recent if s["overall_score"] < min_quality_threshold
        )
        if low_quality_count >= 2:
            logger.info(
                "Debate quality degraded: last 2 rounds below %.2f — early termination",
                min_quality_threshold,
            )
            return "terminate"

        # 观点收敛检测：双方都在最近两轮表示同意/妥协 → 可决策
        converge_score = _detect_convergence(self._round_scores)
        if converge_score >= 1.0:
            logger.info("Debate converged — both sides showing agreement")
            return "terminate"

        return "continue"

    # ------------------------------------------------------------------
    # 便捷方法：从辩论状态自动提取所需信息
    # ------------------------------------------------------------------

    def evaluate_from_state(
        self, debate_state: dict, response: str
    ) -> dict:
        """从 InvestDebateState 中提取上下文并评估本轮质量。

        Args:
            debate_state: InvestDebateState 字典。
            response: 本轮最新发言文本。

        Returns:
            评分字典。
        """
        opponent_history = _extract_opponent_history(debate_state)
        round_number = debate_state.get("count", 0)
        return self.evaluate_round(response, opponent_history, round_number)

    def reset(self):
        """重置评分历史（用于新的辩论会话）。"""
        self._round_scores.clear()


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _extract_opponent_history(debate_state: dict) -> list[str]:
    """从辩论状态中提取对手方的历史发言列表。

    根据 latest_speaker 推断当前方，返回对手方的历史发言。
    """
    latest = debate_state.get("latest_speaker", "")
    # 如果当前是 Bull 刚发言完，对手是 Bear
    # 实际上这是下一轮的上下文：当前方发言时，对手历史是对方历史
    # 简化处理：合并所有 history 中非当前方的发言
    history = debate_state.get("history", "")
    if not history:
        return []

    # 分割为各次发言（以 Analyst 标签为界）
    # 格式: "Bull Analyst: ... \n Bear Analyst: ..."
    segments = re.split(r"\n(?=Bull Analyst:|Bear Analyst:)", history)
    # 去除空段
    segments = [s.strip() for s in segments if s.strip()]

    # latest_speaker 是刚发言的那个，opponent 是另一方
    if latest == "Bull":
        opponent_label = "Bear Analyst:"
    else:
        opponent_label = "Bull Analyst:"

    opponent_responses = [s for s in segments if s.startswith(opponent_label)]

    # 如果无法按标签匹配（首轮无 latest_speaker），fallback 使用所有历史
    if not opponent_responses:
        opponent_responses = segments

    return opponent_responses
