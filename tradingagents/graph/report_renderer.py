"""报告渲染中间件 — 按固定三段式（核心结论→关键数据→风险提示）统一渲染每个 analyst section。

v0.2.15-cn P0：消除不同标的/行业之间的报告风格漂移。
Each analyst 报告 section 内部使用一模一样的骨架结构，不管 LLM 输出什么格式，
最终返回统一的三段式 markdown。

兼容路径：
- executor.py `_extract_report()` → 可替换为 `ReportRenderer.render()`
- schemas.py 的 Pydantic render_* 函数 → 不受影响，作为上游输入
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 分析师 state key → 标题名称映射（与 executor._extract_report 保持一致）
ANALYST_SECTIONS: List[Tuple[str, str]] = [
    ("Market Analyst", "market_report"),
    ("Fundamentals Analyst", "fundamentals_report"),
    ("News Analyst", "news_report"),
    ("Social Analyst", "sentiment_report"),
]

# 用于检测结论段落的章节标题模式
_CONCLUSION_HEADERS = re.compile(
    r"(?:^|\n)#{1,3}\s*(?:核心结论|结论|总结|概要|Summary|Conclusion|Key\s*Takeaway)",
    re.IGNORECASE,
)
# 用于检测风险段落的章节标题模式
_RISK_HEADERS = re.compile(
    r"(?:^|\n)#{1,3}\s*(?:风险|风险提示|风险因素|风险分析|Risk|Risk\s*Factor)",
    re.IGNORECASE,
)
# 提取 markdown 表格行
_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$")
# 提取 key-value 对（如 **PE**: 15.3）
_KV_PAIR = re.compile(r"\*\*([^*]+)\*\*\s*[:：]\s*(.+?)(?:\n|$)")
# 提取前几句作为 fallback 结论
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？])\s*")

# 风险关键词（中文 + 英文）
_RISK_KEYWORDS = [
    "风险", "下行", "不利", "波动", "不确定", "回调", "监管", "退市",
    "risk", "downside", "volatility", "uncertainty", "regulatory",
    "delist", "drawdown", "correction",
]
_RISK_KW_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:[-*]\s*)?(" + "|".join(re.escape(k) for k in _RISK_KEYWORDS) + r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _strip_markdown_fmt(text: str) -> str:
    """移除 markdown 内联格式（粗体、斜体等）但保留文本。"""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


def _first_n_sentences(text: str, n: int = 2) -> str:
    """取文本前 n 个句子作为 fallback 核心结论。"""
    clean = _strip_markdown_fmt(text)
    lines = [l for l in clean.split("\n") if l.strip() and not l.strip().startswith("#")]
    joined = " ".join(lines)
    parts = _SENTENCE_SPLIT.split(joined)
    sentences: List[str] = []
    for p in parts:
        s = p.strip()
        if not s or s.startswith("#") or s in ("。", "！", "？"):
            continue
        if not s[-1] in "。！？":
            s = s + "。"
        sentences.append(s)
        if len(sentences) >= n:
            break
    return "".join(sentences[:n])


def _extract_section_by_header(text: str, header_pattern: re.Pattern) -> Optional[str]:
    """根据正则匹配的 section header 提取该 section 的全部内容（到下一个同级 header 为止）。"""
    lines = text.split("\n")
    start = -1
    header_prefix = ""
    for i, line in enumerate(lines):
        if header_pattern.search(line):
            # 记录 header 的 # 级别
            m = re.match(r"^(#+)\s", line.strip())
            header_prefix = m.group(1) if m else "##"
            start = i
            break
    if start < 0:
        return None

    # 收集从 start+1 到下一个同级别 header 的内容
    same_level_kw = re.compile(r"^" + re.escape(header_prefix) + r"\s")
    content_lines: List[str] = []
    for line in lines[start + 1:]:
        if same_level_kw.match(line.strip()):
            break
        content_lines.append(line)
    return "\n".join(content_lines).strip()


def _extract_table_rows(text: str) -> List[List[str]]:
    """从 markdown 文本中提取表格行（跳过 separator 行）。"""
    rows: List[List[str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not _TABLE_ROW.match(stripped):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", stripped):
            continue  # separator 行
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if cells:
            rows.append(cells)
    return rows


def _extract_kv_pairs(text: str) -> List[Tuple[str, str]]:
    """从文本中提取 **Key**: Value 对。"""
    return _KV_PAIR.findall(text)


def _extract_risk_lines(text: str) -> List[str]:
    """从文本中提取风险相关的 bullet/行。"""
    risks: List[str] = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _RISK_KW_PATTERN.search(stripped):
            # 取该行作为风险条目，去掉 markdown bullet 前缀
            cleaned = re.sub(r"^[-*]\s*", "", stripped)
            cleaned = _strip_markdown_fmt(cleaned)
            if len(cleaned) > 5:
                risks.append(cleaned)
        if len(risks) >= 5:
            break
    return risks[:3]  # 最多 3 条


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_conclusion(conclusion: str) -> str:
    """渲染「核心结论」段落。"""
    text = conclusion.strip() if conclusion else "数据暂缺"
    return f"**核心结论**\n\n{text}"


def _render_key_data(kv_rows: List[Tuple[str, str]]) -> str:
    """渲染「关键数据」markdown 表格。"""
    if not kv_rows:
        return "**关键数据**\n\n数据暂缺"
    header = "**关键数据**"
    table = "| 指标 | 数值 |\n|------|------|\n"
    for key, val in kv_rows:
        # 截断过长的值
        val_display = val.strip()[:80]
        table += f"| {key.strip()} | {val_display} |\n"
    return f"{header}\n\n{table}"


def _render_risks(risks: List[str]) -> str:
    """渲染「风险提示」bullet 列表。"""
    if not risks:
        return "**风险提示**\n\n- 数据暂缺"
    header = "**风险提示**"
    bullets = "\n".join(f"- {r}" for r in risks)
    return f"{header}\n\n{bullets}"


# ---------------------------------------------------------------------------
# Core parsers
# ---------------------------------------------------------------------------

def _parse_report_text(report: str) -> Tuple[str, List[Tuple[str, str]], List[str]]:
    """从自由文本报告中解析（核心结论, 关键数据, 风险提示）。

    策略：
    1. 先查显式章节标题
    2. 回退到启发式算法
    3. 全部失败则用原文前 2 句作为结论
    """
    if not report or not report.strip():
        return ("数据暂缺", [], [])

    # --- Step 1: 显式章节 ---
    conclusion_text = _extract_section_by_header(report, _CONCLUSION_HEADERS)
    risk_text = _extract_section_by_header(report, _RISK_HEADERS)

    # --- Step 2: 提取关键数据（表格 + KV 对）---
    table_rows = _extract_table_rows(report)
    kv_pairs = _extract_kv_pairs(report)

    # 构建统一的 key_data 行
    key_data: List[Tuple[str, str]] = []
    seen_keys: set = set()
    for k, v in kv_pairs:
        k_clean = _strip_markdown_fmt(k).strip()
        if k_clean and k_clean not in seen_keys:
            key_data.append((k_clean, _strip_markdown_fmt(v).strip()))
            seen_keys.add(k_clean)

    # 如果表格有多行（无 KV 对的情况），用表格第一列作为指标名
    if not key_data and len(table_rows) >= 2:
        headers = table_rows[0]
        if headers and len(headers) == 2:
            # 典型两列表格：| 指标 | 数值 | → 直接用 row[0]/row[1]
            for row in table_rows[1:]:
                key = (row[0] if len(row) > 0 else "").strip()
                val = (row[1] if len(row) > 1 else "").strip()
                if key and key not in seen_keys:
                    key_data.append((key, val))
                    seen_keys.add(key)
        elif headers:
            # 多列表格：每列独立作为指标
            for row in table_rows[1:]:
                for j, cell in enumerate(row):
                    label = headers[j] if j < len(headers) else f"列{j+1}"
                    if cell.strip() and label.strip() not in seen_keys:
                        key_data.append((label.strip(), cell.strip()))
                        seen_keys.add(label.strip())

    # --- Step 3: 结论处理 ---
    if not conclusion_text:
        conclusion_text = _first_n_sentences(report, n=2)

    # --- Step 4: 风险处理 ---
    risks: List[str] = []
    if risk_text:
        risk_lines = risk_text.split("\n")
        for line in risk_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                cleaned = re.sub(r"^[-*]\s*", "", stripped)
                cleaned = _strip_markdown_fmt(cleaned)
                if len(cleaned) > 5:
                    risks.append(cleaned)
    if not risks:
        # 从原报告中扫描风险关键词
        risks = _extract_risk_lines(report)
    # 如果扫描结果过多（LLM 自由文本），取前 3 条
    risks = risks[:3]

    return (conclusion_text, key_data, risks)


def _parse_report_dict(report: dict) -> Tuple[str, List[Tuple[str, str]], List[str]]:
    """从结构化 dict 中提取（核心结论, 关键数据, 风险提示）。

    支持多种 dict 结构：
    - Pydantic model 序列化后的 dict（如 MarketReport）
    - 自定义 dict 包含 conclusion / key_data / risks
    """
    # 尝试常见 key
    conclusion = ""
    risks: List[str] = []
    key_data: List[Tuple[str, str]] = []

    # 核心结论: 多种可能的字段名
    for key in ("executive_summary", "conclusion", "summary", "key_findings", "investment_thesis"):
        val = report.get(key)
        if val:
            if isinstance(val, list):
                conclusion = "；".join(str(v) for v in val)
            else:
                conclusion = str(val)
            break

    # 如果没找到结论，尝试 markdown_body 的前几句
    if not conclusion:
        body = report.get("markdown_body", "") or report.get("content", "") or ""
        if body:
            conclusion = _first_n_sentences(str(body), n=2)

    # 关键数据: 尝试 key_metrics / indicators / data 字段
    metrics = report.get("key_metrics", None) or report.get("metrics", None)
    if isinstance(metrics, dict):
        for k, v in metrics.items():
            key_data.append((str(k), str(v)))
    elif isinstance(metrics, list) and metrics and isinstance(metrics[0], dict):
        # list of dicts: [{name: "PE", value: 15}, ...]
        for item in metrics:
            name = item.get("name", item.get("indicator", item.get("key", "")))
            val = item.get("value", item.get("val", ""))
            if name:
                key_data.append((str(name), str(val)))

    # 如果没有 key_data，从 markdown_body 提取 KV 对
    if not key_data:
        body = report.get("markdown_body", "") or report.get("content", "") or ""
        if body:
            key_data = _extract_kv_pairs(str(body))

    # 风险: 多种可能的字段名
    for key in ("risks", "risk_factors", "risk", "warnings"):
        val = report.get(key)
        if val:
            if isinstance(val, list):
                risks = [str(v) for v in val]
            else:
                risks = [str(val)]
            break

    # 如果没找到风险，从 markdown_body 提取
    if not risks:
        body = report.get("markdown_body", "") or report.get("content", "") or ""
        if body:
            risks = _extract_risk_lines(str(body))

    return (conclusion or "数据暂缺", key_data, risks[:3])


# ---------------------------------------------------------------------------
# ReportRenderer
# ---------------------------------------------------------------------------


class ReportRenderer:
    """统一报告渲染器 — 每个 analyst section 三段式骨架。

    用法::

        from tradingagents.graph.report_renderer import ReportRenderer

        # 方式 1: 直接渲染完整报告（替换 executor._extract_report）
        report = ReportRenderer.render(agent_states, plan)

        # 方式 2: 仅渲染单个 section
        section = ReportRenderer.render_section("Market Analyst", market_report_text)
    """

    @staticmethod
    def render_section(analyst_name: str, report: Union[str, dict]) -> str:
        """统一渲染一个 analyst section。

        Args:
            analyst_name: analyst 标题（如 "Market Analyst"）。
            report: 报告内容，可以是自由文本（str）或结构化数据（dict）。

        Returns:
            三段式 markdown（核心结论 → 关键数据 → 风险提示）。

        示例输出::

            **核心结论**

            技术面呈现多头排列，MACD金叉确认，成交量温和放大。

            **关键数据**

            | 指标 | 数值 |
            |------|------|
            | RSI(14) | 62.5 |
            | MACD | 金叉 |

            **风险提示**

            - 成交量未能有效放大，突破可能为假信号
            - RSI 接近超买区域，短线回调风险
        """
        if isinstance(report, dict):
            conclusion, key_data, risks = _parse_report_dict(report)
        else:
            conclusion, key_data, risks = _parse_report_text(report)

        parts = [
            _render_conclusion(conclusion),
            "",
            _render_key_data(key_data),
            "",
            _render_risks(risks),
        ]
        return "\n".join(parts)

    @staticmethod
    def render(
        reports: Dict[str, Any],
        plan: Optional[Dict[str, Any]] = None,
    ) -> str:
        """组装完整分析报告。

        包含：所有 analyst section + investment_plan + trader_plan + final_decision。

        Args:
            reports: agent_states 字典（含 market_report / fundamentals_report /
                     news_report / sentiment_report / investment_plan /
                     trader_investment_plan / final_trade_decision）。
            plan: 可选的计划上下文（用于增强报告元信息）。

        Returns:
            完整 markdown 报告字符串。

        兼容性：
            完全兼容 ``executor.GraphExecutor._extract_report(final_state: dict)``
            的调用签名。直接替换即可::

                # 旧代码
                report = self._extract_report(final_state)

                # 新代码
                from tradingagents.graph.report_renderer import ReportRenderer
                report = ReportRenderer.render(final_state, plan)
        """
        parts: List[str] = []

        # 1. 各 analyst section
        for title, state_key in ANALYST_SECTIONS:
            content = reports.get(state_key, "")
            if not content:
                continue
            rendered = ReportRenderer.render_section(title, content)
            parts.append(f"--- {title} ---\n\n{rendered}")

        # 2. Investment Plan
        investment_plan = reports.get("investment_plan", "")
        if investment_plan:
            parts.append(f"--- Investment Plan ---\n\n{investment_plan}")

        # 3. Trader Plan
        trader_plan = reports.get("trader_investment_plan", "")
        if trader_plan:
            parts.append(f"--- Trader Plan ---\n\n{trader_plan}")

        # 4. Final Decision（仅当与 investment_plan 不同时）
        final_decision = reports.get("final_trade_decision", "")
        if final_decision and final_decision != investment_plan:
            parts.append(f"--- Final Decision ---\n\n{final_decision}")

        return "\n\n".join(parts) if parts else ""
