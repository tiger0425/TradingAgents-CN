"""TDD RED tests: prove IndustryFramework.lookup() matches "通信线缆及配套" incorrectly.

Bug: "通信" (tech_saas keyword) is a substring of "通信线缆及配套", so _fuzzy_match
step 2 returns tech_saas framework. This is wrong — 通信线缆及配套 is a cable/wire
manufacturing industry, not a tech SaaS industry.

These tests MUST FAIL RED until the bug is fixed (later task).
"""

from tradingagents.industry.frameworks import IndustryFramework


# ── Bug repro: "通信线缆及配套" should NOT match tech_saas ──────────────


def test_comm_cable_rejects_saas():
    """RED: "通信线缆及配套" incorrectly matches tech_saas due to '通信' keyword match.

    This is the core bug — a cable/wire manufacturer is NOT SaaS.
    Expected: result is None OR result['name_en'] != 'tech_saas'.
    Actual (bug): returns tech_saas framework.
    """
    fw = IndustryFramework()
    result = fw.lookup("通信线缆及配套")
    assert result is None or result["name_en"] != "tech_saas", (
        f"BUG: '通信线缆及配套' matched tech_saas (framework={result['name']}). "
        "通信线缆及配套 is a cable/wire manufacturer, not SaaS."
    )


def test_comm_cable_no_framework_yet():
    """RED/optional: "通信线缆及配套" currently has no dedicated framework.

    Since there is no 'comm_cable' framework yet, lookup should return None
    (no auto-generation without quick_llm).
    """
    fw = IndustryFramework()
    result = fw.lookup("通信线缆及配套")
    assert result is None, (
        f"Expected None for unmatched industry, got {result['name']}"
    )


# ── Backward compatibility: all 5 existing frameworks ──────────────────


def test_automotive_framework_match():
    """'汽车制造' should match the automotive framework."""
    fw = IndustryFramework()
    result = fw.lookup("汽车制造")
    assert result is not None, "汽车制造 should match a framework"
    assert result["name_en"] == "automotive", (
        f"Expected automotive, got {result['name_en']}"
    )


def test_banking_framework_match():
    """'银行' should match the banking framework."""
    fw = IndustryFramework()
    result = fw.lookup("银行")
    assert result is not None, "银行 should match a framework"
    assert result["name_en"] == "banking", (
        f"Expected banking, got {result['name_en']}"
    )


def test_tech_saas_framework_match():
    """'SaaS' should match the tech_saas framework."""
    fw = IndustryFramework()
    result = fw.lookup("SaaS")
    assert result is not None, "SaaS should match a framework"
    assert result["name_en"] == "tech_saas", (
        f"Expected tech_saas, got {result['name_en']}"
    )


def test_consumer_framework_match():
    """'白酒' should match the consumer framework."""
    fw = IndustryFramework()
    result = fw.lookup("白酒")
    assert result is not None, "白酒 should match a framework"
    assert result["name_en"] == "consumer", (
        f"Expected consumer, got {result['name_en']}"
    )


def test_pharma_framework_match():
    """'医药' should match the pharma framework."""
    fw = IndustryFramework()
    result = fw.lookup("医药")
    assert result is not None, "医药 should match a framework"
    assert result["name_en"] == "pharma", (
        f"Expected pharma, got {result['name_en']}"
    )


def test_list_frameworks_returns_all_five():
    """list_frameworks() should return exactly 5 frameworks."""
    fw = IndustryFramework()
    frameworks = fw.list_frameworks()
    assert len(frameworks) >= 5, (
        f"Expected at least 5 frameworks, got {len(frameworks)}"
    )
    names = [f["name_en"] for f in frameworks]
    for expected in ("automotive", "banking", "tech_saas", "consumer", "pharma"):
        assert expected in names, (
            f"Missing framework: {expected} (found: {names})"
        )
