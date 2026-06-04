"""TDD RED/verification tests: normalize_injection() contract.

Tests validate the behavior of normalize_injection() which will be created
in tradingagents/industry/injection_contract.py.

The function normalizes industry anti-patterns and correct metrics:
  - Truncates anti_patterns list to ≤5 items when ≥7 provided
  - Truncates each line to ≤30 characters
  - Truncates correct_metrics to ≤8 items
  - Returns "" for empty input
  - Returns output prefixed with "##INDUSTRY_GUIDE##" when non-empty

RED phase: injection_contract.py does NOT exist yet, so ALL tests fail
with ModuleNotFoundError on import.
"""

import pytest


def test_normalize_injection_truncates_anti_patterns():
    """normalize_injection() truncates ≥7 anti_patterns to ≤5.

    When 7 or more anti_patterns are provided, the function must keep
    only the first 5 and discard the rest.
    """
    from tradingagents.industry.injection_contract import normalize_injection

    anti_patterns = [
        "禁止使用行业指标A",
        "禁止使用行业指标B",
        "禁止使用行业指标C",
        "禁止使用行业指标D",
        "禁止使用行业指标E",
        "禁止使用行业指标F",
        "禁止使用行业指标G",
    ]
    correct_metrics = ["正确指标1", "正确指标2"]
    result = normalize_injection(anti_patterns, correct_metrics)

    # Split into lines, skip the header
    lines = [l for l in result.split("\n") if l.strip() and not l.startswith("##")]
    anti_pattern_lines = [l for l in lines if "禁止" in l]
    assert len(anti_pattern_lines) <= 5, (
        f"Expected ≤5 anti-pattern lines after truncation, "
        f"got {len(anti_pattern_lines)}: {anti_pattern_lines}"
    )


def test_normalize_injection_truncates_long_lines():
    """normalize_injection() truncates each line to ≤30 characters.

    If any anti-pattern or correct-metric line exceeds 30 characters,
    the function must truncate it (Chinese text uses len() for character
    count, not word count).
    """
    from tradingagents.industry.injection_contract import normalize_injection

    anti_patterns = ["这是一个超过三十个字符的非常长的禁止使用行业指标"]
    correct_metrics = ["这是一个超过三十个字符的非常长的正确行业指标描述"]
    result = normalize_injection(anti_patterns, correct_metrics)

    for line in result.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("##"):
            continue
        assert len(stripped) <= 30, (
            f"Expected each line ≤30 characters, "
            f"got {len(stripped)} chars: {repr(stripped)}"
        )


def test_normalize_injection_handles_empty():
    """normalize_injection() returns "" when both inputs are empty.

    When anti_patterns and correct_metrics are both empty lists,
    the function must return an empty string.
    """
    from tradingagents.industry.injection_contract import normalize_injection

    result = normalize_injection([], [])
    assert result == "", (
        f"Expected empty string for empty inputs, "
        f"got {repr(result)}"
    )


def test_normalize_injection_output_starts_with_header():
    """normalize_injection() output starts with "##INDUSTRY_GUIDE##" when non-empty.

    When anti_patterns or correct_metrics is non-empty, the output must
    begin with the standard industry guide header.
    """
    from tradingagents.industry.injection_contract import normalize_injection

    result = normalize_injection(["禁止使用指标A"], ["正确指标1"])
    assert result.startswith("##INDUSTRY_GUIDE##"), (
        f"Expected output to start with '##INDUSTRY_GUIDE##', "
        f"got {repr(result[:50])}"
    )


def test_normalize_injection_truncates_correct_metrics():
    """normalize_injection() truncates correct_metrics to ≤8 items.

    When more than 8 correct_metrics are provided, the function must
    keep only the first 8 and discard the rest.
    """
    from tradingagents.industry.injection_contract import normalize_injection

    anti_patterns = ["禁止使用指标A"]
    correct_metrics = [f"正确指标{i}" for i in range(1, 12)]
    result = normalize_injection(anti_patterns, correct_metrics)

    # Split into lines, skip the header
    lines = [l for l in result.split("\n") if l.strip() and not l.startswith("##")]
    metric_lines = [l for l in lines if "正确指标" in l]
    assert len(metric_lines) <= 8, (
        f"Expected ≤8 correct-metric lines after truncation, "
        f"got {len(metric_lines)}: {metric_lines}"
    )
