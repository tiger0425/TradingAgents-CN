"""Industry injection contract — normalizes anti-patterns and correct metrics.

The normalize_injection() function enforces a contract on industry framework
data before it's injected into agent prompts:

  - Anti-patterns: max 5 items, each line max 30 characters
  - Correct metrics: max 8 items
  - Empty input -> ""
  - Non-empty output -> prefixed with ##INDUSTRY_GUIDE## header
"""


def normalize_injection(
    anti_patterns: list[str], correct_metrics: list[str]
) -> str:
    """Normalize anti-patterns and correct metrics into a standardized string.

    Args:
        anti_patterns: List of anti-pattern strings to normalize.
        correct_metrics: List of correct metric strings to normalize.

    Returns:
        Normalized string with ##INDUSTRY_GUIDE## header (if non-empty),
        or empty string if both inputs are empty.
    """
    # Truncate anti_patterns to max 5 items, each line max 30 chars
    truncated_anti = [ap[:30] for ap in anti_patterns[:5]]

    # Truncate correct_metrics to max 8 items
    truncated_metrics = correct_metrics[:8]

    # Empty input -> return ""
    if not truncated_anti and not truncated_metrics:
        return ""

    # Build output with header
    lines = ["##INDUSTRY_GUIDE##"]
    lines.extend(truncated_anti)
    lines.extend(truncated_metrics)
    return "\n".join(lines)
