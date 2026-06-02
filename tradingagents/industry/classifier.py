"""IndustryClassifier — structured wrapper around get_industry()."""

import re
from dataclasses import dataclass

from tradingagents.dataflows.a_stock_data import get_industry


@dataclass
class IndustryResult:
    """Structured industry classification result.

    Follows the dataclass pattern from tradingagents.planner.schemas.

    Attributes:
        primary: Main industry category (e.g. "白酒", "汽车制造").
        secondary: Sub-category or tier suffix (e.g. "Ⅱ" for "白酒Ⅱ").
        confidence: Confidence score 0.0–1.0.
        source: Data source identifier (e.g. "a_stock_data", "fallback").
    """
    primary: str = ""
    secondary: str = ""
    confidence: float = 0.0
    source: str = ""


# Roman numerals commonly used in Chinese industry sub-classifications
_ROMAN_PATTERN = re.compile(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+$")


def _split_primary_secondary(raw: str) -> tuple[str, str]:
    """Split a raw industry name into primary + secondary.

    Examples:
        "白酒Ⅱ"    → ("白酒", "Ⅱ")
        "商用载货车" → ("商用载货车", "")
        "汽车制造"  → ("汽车制造", "")
    """
    raw = raw.strip()
    match = _ROMAN_PATTERN.search(raw)
    if match:
        secondary = match.group()
        primary = raw[:match.start()].strip()
        return primary, secondary
    return raw, ""


class IndustryClassifier:
    """Classifies a stock ticker into a structured IndustryResult.

    Delegates to get_industry() from a_stock_data for the underlying
    data retrieval (mootdx F10 → EastMoney → F10 regex fallback),
    then wraps the result in a structured dataclass.
    """

    def classify(self, code: str) -> IndustryResult:
        """Classify the industry of a stock by its ticker code.

        Args:
            code: Stock ticker code, e.g. "600418", "600519".

        Returns:
            IndustryResult with parsed industry information.
            Never raises — degrades gracefully on any failure.
        """
        try:
            raw = get_industry(code)
        except Exception:
            return IndustryResult(
                primary="未知",
                confidence=0.0,
                source="fallback",
            )

        if not raw or raw == "未知":
            return IndustryResult(
                primary="未知",
                confidence=0.0,
                source="fallback",
            )

        primary, secondary = _split_primary_secondary(raw)
        return IndustryResult(
            primary=primary,
            secondary=secondary,
            confidence=1.0,
            source="a_stock_data",
        )
