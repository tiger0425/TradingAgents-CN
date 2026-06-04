"""Industry classification verifier.

Validates and sanity-checks industry classification results.
Provides two-tier consistency verification:
  1. Rule-based anti-pattern keyword detection (fast, no LLM)
  2. LLM-based semantic fallback (deeper check when rules are inconclusive)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .classifier import IndustryResult
from .frameworks import IndustryFramework

logger = logging.getLogger(__name__)


class IndustryVerifier:
    """Verifies the consistency and plausibility of industry results."""

    @staticmethod
    def is_known(result: IndustryResult) -> bool:
        """Check whether the classification resolved to a known industry."""
        return bool(result.primary) and result.primary != "未知"

    @staticmethod
    def is_confident(result: IndustryResult, threshold: float = 0.5) -> bool:
        """Check whether confidence meets a threshold."""
        return result.confidence >= threshold

    # ── Public API ─────────────────────────────────────────────────────

    @staticmethod
    def verify_industry_consistency(
        industry: str,
        report: str,
        quick_llm: Any = None,
    ) -> dict[str, Any]:
        """Verify that a report's metrics match the detected industry framework.

        Two-tier verification:
          1. **Rule layer** (always runs, no LLM cost):
             - Looks up the industry framework via ``IndustryFramework.lookup()``
             - If a framework is found, scans *report* for each anti-pattern
               keyword (case-insensitive).
             - If any anti-patterns match → return ``consistent=False``
               immediately with ``method="rules"``.
          2. **LLM fallback** (only when rules are inconclusive):
             - When a framework exists but NO anti-patterns were matched,
               the rules result is inconclusive (the anti-pattern list may
               be incomplete).  If *quick_llm* is provided, a single
               structured-output call performs a deeper semantic check.
             - If *quick_llm* is not available, default to ``consistent=True``.

        Args:
            industry: Detected industry name (e.g. ``"汽车制造"``, ``"白酒"``).
            report: Full analysis report text to check.
            quick_llm: Optional LangChain-compatible LLM for the semantic
                fallback.  If ``None`` the LLM tier is skipped.

        Returns:
            A dict with four keys::

                {
                    "consistent": bool,   # True when no issues found
                    "issues": list[str],  # Human-readable issue descriptions
                    "severity": str,      # "error" (rules) | "warning" (LLM)
                    "method": str,        # "rules" | "llm"
                }
        """
        # ── Guard: empty inputs ─────────────────────────────────────────
        if not industry or not report:
            return _CONSISTENT_DEFAULT

        # ── Tier 1: Rule-based anti-pattern detection ───────────────────
        fw = IndustryFramework().lookup(industry)

        # No matching framework = no basis for consistency checking
        if fw is None:
            return _CONSISTENT_DEFAULT

        anti_patterns = fw.get("anti_patterns", [])
        report_lower = report.lower()
        found = [ap for ap in anti_patterns if ap.lower() in report_lower]

        if found:
            issues = [
                f"Report contains '{ap}' not applicable to {industry}"
                for ap in found
            ]
            return {
                "consistent": False,
                "issues": issues,
                "severity": "error",
                "method": "rules",
            }

        # ── Tier 2: LLM semantic fallback ───────────────────────────────
        if quick_llm is not None:
            return _llm_check(quick_llm, industry, report)

        return _CONSISTENT_DEFAULT

    # ── Metric traceability ──────────────────────────────────────────

    @staticmethod
    def verify_metric_sources(
        report: str,
        tool_messages: list[dict],
    ) -> dict[str, Any]:
        """Verify that financial metrics in report are traceable to tool outputs.

        Extracts numbers from the report and checks whether each number can
        be found (as a string) in the content of any tool-provided message.
        Numbers that cannot be traced back are flagged as potential LLM
        hallucinations.

        Automatically handles percentage ↔ decimal conversions (e.g. 91.5%
        in the report → 0.915 in tool data).

        Returns:
            dict with ``verdict`` (pass/warn/fail), ``issues`` (list[str]),
            and ``method`` (always ``"metric_trace"``).
        """
        if not report or not tool_messages:
            return {"verdict": "pass", "issues": [], "method": "metric_trace"}

        raw_numbers = re.findall(r"\b\d+\.?\d*\b", report)

        year_re = re.compile(r"^(?:19|20)\d{2}$")
        numbers = [n for n in raw_numbers if not year_re.match(n)]

        tool_content = " ".join(
            str(msg.get("content", "")) for msg in tool_messages
        )

        issues: list[str] = []
        for num_str in numbers:
            num_val = float(num_str)
            found = False

            if num_str in tool_content:
                found = True
            elif num_val >= 1:
                decimal_val = num_val / 100
                for fmt in (str(decimal_val),
                            f"{decimal_val:.1f}",
                            f"{decimal_val:.2f}",
                            f"{decimal_val:.3f}"):
                    if fmt in tool_content:
                        found = True
                        break
            elif 0 < num_val < 1:
                pct_val = num_val * 100
                for fmt in (str(pct_val),
                            f"{pct_val:.0f}",
                            f"{pct_val:.1f}"):
                    if fmt in tool_content:
                        found = True
                        break

            if not found:
                idx = report.find(num_str)
                start = max(0, idx - 25)
                end = min(len(report), idx + len(num_str) + 25)
                ctx = report[start:end].strip()
                issues.append(
                    f"数值 {num_str} 在工具返回数据中未找到来源: ...{ctx}..."
                )

        if issues:
            return {"verdict": "warn", "issues": issues, "method": "metric_trace"}
        return {"verdict": "pass", "issues": [], "method": "metric_trace"}

    # ── Foreign‑term detection ───────────────────────────────────────

    @staticmethod
    def detect_foreign_terms(
        report: str,
        market: str = "A_SHARE",
    ) -> dict[str, Any]:
        """Detect foreign-market regulatory / industry terms in a report.

        A‑share analysis reports should not contain US‑centric or
        foreign‑market terms (EPA, SEC, Class 8, etc.).  The presence
        of such terms strongly indicates LLM hallucination of a
        foreign‑market context.

        Returns:
            dict with ``verdict`` (pass/fail), ``issues`` (list[str]),
            and ``method`` (always ``"foreign_terms"``).
        """
        if not report:
            return {"verdict": "pass", "issues": [], "method": "foreign_terms"}

        _foreign_terms: dict[str, list[str]] = {
            "A_SHARE": [
                "EPA",
                "EPA 2027",
                "EPA 2030",
                "Class 8",
                "ACT Research",
                "Class A RV",
                "SAE",
                "NHTSA",
                "FMCSA",
                "DOT regulation",
                "CARB",
                "GHG Phase",
                "SEC filing",
                "NYSE",
                "NASDAQ",
                "S&P 500",
                "Dow Jones",
                "NASDAQ-100",
                "Russell 2000",
                "FOMC",
                "Federal Reserve rate",
            ],
        }

        terms = _foreign_terms.get(market, _foreign_terms["A_SHARE"])
        report_lower = report.lower()
        issues: list[str] = []

        for term in terms:
            if term.lower() in report_lower:
                issues.append(
                    f"发现非{market}市场术语: '{term}'，"
                    f"可能为LLM幻觉生成的境外市场内容"
                )

        if issues:
            return {"verdict": "fail", "issues": issues, "method": "foreign_terms"}
        return {"verdict": "pass", "issues": [], "method": "foreign_terms"}

    # ── Cross‑report contradiction detection ─────────────────────────

    @staticmethod
    def detect_cross_report_contradictions(
        reports: list[dict],
    ) -> dict[str, Any]:
        """Detect contradictory bullish vs bearish sentiment across reports.

        When one report expresses bullish sentiment but another report
        on the same instrument is bearish, the verifier flags a
        cross‑report contradiction.

        Returns:
            dict with ``verdict`` (pass/warn), ``issues`` (list[str]),
            and ``method`` (always ``"cross_report"``).
        """
        if not reports or len(reports) < 2:
            return {"verdict": "pass", "issues": [], "method": "cross_report"}

        bullish_terms = ["看涨", "bullish", "看多", "强烈看涨"]
        bearish_terms = ["看跌", "bearish", "看空", "强烈看跌"]

        bullish_agents: list[str] = []
        bearish_agents: list[str] = []

        for r in reports:
            content = r.get("content", "")
            agent = r.get("agent", "unknown")
            content_lower = content.lower()

            is_bullish = any(t in content for t in bullish_terms) or \
                         any(t.lower() in content_lower for t in ["bullish"])
            is_bearish = any(t in content for t in bearish_terms) or \
                         any(t.lower() in content_lower for t in ["bearish"])

            if is_bullish:
                bullish_agents.append(agent)
            if is_bearish:
                bearish_agents.append(agent)

        if bullish_agents and bearish_agents:
            issue = (
                f"跨报告矛盾: {bullish_agents} 看涨 vs {bearish_agents} 看跌，"
                f"同一次分析中存在方向性冲突"
            )
            return {"verdict": "warn", "issues": [issue], "method": "cross_report"}

        return {"verdict": "pass", "issues": [], "method": "cross_report"}


# ── Module-level constants ──────────────────────────────────────────────

_CONSISTENT_DEFAULT: dict[str, Any] = {
    "consistent": True,
    "issues": [],
    "severity": "warning",
    "method": "rules",
}


# ── LLM fallback helpers ───────────────────────────────────────────────

_LLM_SYSTEM_PROMPT = (
    '你是一个行业分析校验器。请判断报告内容是否与给定行业匹配。'
    '仅返回JSON，不要附加任何其他文字。'
)

_LLM_USER_TEMPLATE = (
    '行业: {industry}\n'
    '报告摘要:\n{truncated}\n\n'
    '请判断报告中的分析指标和关注点是否属于该行业的合理范围。\n'
    '仅返回JSON格式:\n'
    '{{"consistent": true/false, "issues": ["问题1", "问题2"]}}'
)


def _llm_check(
    quick_llm: Any,
    industry: str,
    report: str,
) -> dict[str, Any]:
    """Run a single LLM call for semantic consistency verification.

    Gracefully degrades to ``consistent=True`` on any failure (parse error,
    network error, exception) so that a transient LLM outage never produces
    a false-positive industry mismatch.
    """
    truncated = report[:2000]
    prompt = _LLM_USER_TEMPLATE.format(industry=industry, truncated=truncated)

    try:
        response = quick_llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_response(text)

        if parsed is not None:
            return {
                "consistent": bool(parsed.get("consistent", True)),
                "issues": list(parsed.get("issues", [])),
                "severity": "warning",
                "method": "llm",
            }
        logger.warning(
            "LLM response did not contain parseable JSON: %.200s", text,
        )
    except Exception as exc:
        logger.warning("LLM consistency check failed: %s", exc)

    # Degrade gracefully
    return {
        "consistent": True,
        "issues": [],
        "severity": "warning",
        "method": "llm",
    }


def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Extract a JSON dict from an LLM response that may contain markdown."""
    text = text.strip()

    # 1. Whole response is JSON
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 2. JSON fenced in ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Any top-level {...} block
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
