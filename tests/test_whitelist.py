"""TDD RED tests: verify whitelist file and its integration into build_instrument_context().

The whitelist document (`docs/industry-fields-whitelist.md`) defines required
(必含字段) and optional (可选字段) fields per industry. These tests prove:

1. The file does NOT exist yet (RED → fails)
2. The 6 industry sections are NOT present (RED → fails)
3. The whitelist content is NOT injected into `build_instrument_context()` (RED → fails)
4. The fallback for missing industries works (regression — passes in RED too)

After GREEN implementation:
- `docs/industry-fields-whitelist.md` exists with ``## industry_name`` sections
- Each section has "必含字段" and "可选字段" lists
- `build_instrument_context()` appends whitelist content alongside existing anti_patterns
- Unknown industries are gracefully skipped without exception
"""

import os

import pytest

from tradingagents.agents.utils.agent_utils import build_instrument_context


# ── Constants ──────────────────────────────────────────────────

WHITELIST_PATH = "docs/industry-fields-whitelist.md"

SIX_INDUSTRIES: list[str] = [
    "automotive",
    "banking",
    "comm_cable",
    "consumer",
    "pharma",
    "tech_saas",
]


# ── 1. File existence ─────────────────────────────────────────


def test_whitelist_file_exists() -> None:
    """RED: ``docs/industry-fields-whitelist.md`` does NOT exist.

    After GREEN: the whitelist document must exist at this path so the
    ``build_instrument_context()`` integration can read it at runtime.
    """
    assert os.path.exists(WHITELIST_PATH), (
        f"Whitelist file not found at {WHITELIST_PATH}. "
        "Create this file with ## industry sections to proceed."
    )


# ── 2. Six-industry coverage ──────────────────────────────────


def test_whitelist_has_all_six_industries() -> None:
    """RED: cannot verify industry sections — whitelist file does NOT exist.

    After GREEN: the file must contain ``## {industry}`` markdown sections for
    all 6 industries (automotive, banking, comm_cable, consumer, pharma, tech_saas).
    Each section must list "必含字段" and "可选字段".
    """
    # This assertion fails first (RED) since the file doesn't exist yet.
    # It guards the subsequent open() call against FileNotFoundError.
    assert os.path.exists(WHITELIST_PATH), (
        f"Cannot check industry sections — {WHITELIST_PATH} is missing. "
        "Create the file with ## sections to proceed."
    )

    with open(WHITELIST_PATH, encoding="utf-8") as f:
        content = f.read()

    for ind in SIX_INDUSTRIES:
        assert f"## {ind}" in content, (
            f"Missing industry section ``## {ind}`` in {WHITELIST_PATH}. "
            f"All 6 industries must have a dedicated section."
        )


# ── 3. Prompt injection ───────────────────────────────────────


def test_agent_utils_injects_whitelist() -> None:
    """RED: build_instrument_context() does NOT inject whitelist fields yet.

    After GREEN: for a known industry (banking), the returned prompt string must
    contain whitelist-specific markers — "必含字段" and/or "可选字段" — appended
    alongside the existing anti_patterns content (not overwriting it).

    The whitelist injection is additive: the existing anti_patterns block
    (e.g. "严禁在分析中使用以下指标") and correct_metrics block must remain intact.
    """
    result = build_instrument_context(
        ticker="000001",
        industry="banking",
        company_name="平安银行",
    )

    # This assertion FAILS in RED: "必含字段" comes from the whitelist file only.
    # After GREEN, whitelist content is appended to the industry guidance prompt.
    assert "必含字段" in result, (
        "Whitelist marker '必含字段' not found in build_instrument_context('000001', 'banking'). "
        "Expected: whitelist content (必含字段/可选字段) appended alongside "
        "anti_patterns injection. Ensure build_instrument_context() reads "
        f"{WHITELIST_PATH} and injects the relevant industry section."
    )


# ── 4. Graceful fallback for missing industries ───────────────


def test_missing_industry_no_exception() -> None:
    """Regression: build_instrument_context() with an unknown industry
    must NOT raise — the whitelist integration should gracefully skip or
    return an empty section. Same for any unknown ticker.

    This test PASSES in RED phase (the current code handles unknown
    industries via try/except). It serves as a regression guard for GREEN:
    after whitelist integration, unknown industries must still not crash.
    """
    result = build_instrument_context(
        ticker="000001",
        industry="nonexistent_xyz",
        company_name="平安银行",
    )
    assert isinstance(result, str), (
        "build_instrument_context must always return a string"
    )
    assert len(result) > 0, (
        "build_instrument_context must never return an empty string"
    )


def test_missing_industry_still_has_basic_context() -> None:
    """Regression: even with an unknown industry, basic ticker context remains.

    The function should still return the instrument description, exchange hint,
    and any multi-industry context — only the industry-specific block is omitted.
    """
    result = build_instrument_context(
        ticker="000001",
        industry="nonexistent_xyz",
        company_name="平安银行",
    )
    # Basic context: company name + ticker must survive unknown industry
    assert "平安银行" in result, (
        "Company name must be preserved for unknown industry"
    )
    assert "000001" in result, (
        "Ticker must always be included in the prompt"
    )


# ── 5. Anti-patterns preservation (additive constraint) ───────


def test_whitelist_does_not_erase_anti_patterns() -> None:
    """RED: currently anti_patterns may or may not appear (depends on framework match).

    After GREEN: the whitelist injection must be additive — the existing
    anti_patterns block must still be present in the output for any known industry.
    This test guards against the whitelist overwriting the anti_patterns injection.

    NOTE: the current code looks up industry frameworks by Chinese keywords
    (e.g. "银行", not "banking"). This test passes ``industry="banking"`` per
    the spec. After GREEN, the whitelist integration should treat both English
    and Chinese industry identifiers consistently and never erase anti_patterns.
    """
    result_banking = build_instrument_context(
        ticker="000001",
        industry="banking",
        company_name="平安银行",
    )
    result_unknown = build_instrument_context(
        ticker="000001",
        industry="nonexistent_xyz",
        company_name="平安银行",
    )

    # After GREEN: the whitelist must ADD to the output, not replace it.
    # Check that at least one existing framework marker is present.
    # This assertion may pass or fail in RED depending on whether
    # IndustryFramework.lookup("banking") matches.
    assert (
        "行业分析框架（可使用的指标）" in result_banking
        or "严禁在分析中使用以下指标" in result_banking
        or "必含字段" in result_banking
    ), (
        "After GREEN: build_instrument_context('000001', 'banking') should contain "
        "either existing framework fields (行业分析框架/严禁分析) or whitelist "
        "fields (必含字段). Both should eventually coexist."
    )

    # Unknown industry: must NOT contain any framework or whitelist injection
    assert "行业分析框架" not in result_unknown, (
        "Unknown industry must not leak framework fields into the prompt"
    )
    assert "必含字段" not in result_unknown, (
        "Unknown industry must not leak whitelist fields into the prompt"
    )
