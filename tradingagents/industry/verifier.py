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
