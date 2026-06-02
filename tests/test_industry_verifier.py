"""Tests for IndustryVerifier consistency check.

TDD: RED (tests) → GREEN (implementation).
"""

import json
from unittest.mock import MagicMock

from tradingagents.industry.verifier import IndustryVerifier


class TestVerifyIndustryConsistency:
    """Rule-based anti-pattern detection + LLM fallback checks."""

    # ── Rule-based tests ────────────────────────────────────────────────

    def test_auto_report_with_saas_anti_patterns(self):
        """Auto industry report containing SaaS keywords → inconsistent (rules)."""
        report = "600418 TOP100客户留存率99% 续约率85% LTV/CAC=3.2"
        result = IndustryVerifier.verify_industry_consistency("汽车制造", report)

        assert result["consistent"] is False
        assert len(result["issues"]) >= 1
        # At least one anti-pattern should be caught
        assert any("续约率" in issue or "TOP100客户" in issue for issue in result["issues"])
        assert result["severity"] == "error"
        assert result["method"] == "rules"

    def test_auto_report_with_correct_metrics(self):
        """Auto industry report with correct metrics → consistent (rules fallback)."""
        report = "600418 月度销量增长15% 产能利用率80% 毛利率提升至18%"
        result = IndustryVerifier.verify_industry_consistency("汽车制造", report)

        assert result["consistent"] is True
        assert result["issues"] == []
        # No anti-pattern found but no LLM → method="rules"
        assert result["method"] == "rules"

    def test_unknown_industry_returns_consistent(self):
        """Unknown industry → consistent (nothing to check against)."""
        report = "营收增长15% 净利润增长20%"
        result = IndustryVerifier.verify_industry_consistency("未知", report)

        assert result["consistent"] is True
        assert result["issues"] == []
        assert result["method"] == "rules"

    def test_banking_report_with_manufacturing_metrics(self):
        """Banking report with manufacturing anti-patterns → inconsistent."""
        report = "该银行产能利用率85% 原材料成本占比提升至60%"
        result = IndustryVerifier.verify_industry_consistency("银行", report)

        assert result["consistent"] is False
        assert len(result["issues"]) >= 1
        assert result["severity"] == "error"
        assert result["method"] == "rules"

    def test_multiple_anti_patterns_all_reported(self):
        """All matching anti-patterns should be listed in issues."""
        report = "续约率下降 ARR不及预期 LTV/CAC恶化 TOP100客户流失"
        result = IndustryVerifier.verify_industry_consistency("汽车制造", report)

        assert result["consistent"] is False
        assert len(result["issues"]) >= 2  # at least a few captured
        assert result["method"] == "rules"

    # ── Edge cases ──────────────────────────────────────────────────────

    def test_empty_industry_returns_consistent(self):
        """Empty industry string → consistent (no-op)."""
        result = IndustryVerifier.verify_industry_consistency("", "some report")
        assert result["consistent"] is True
        assert result["issues"] == []

    def test_empty_report_returns_consistent(self):
        """Empty report string → consistent (no-op)."""
        result = IndustryVerifier.verify_industry_consistency("汽车", "")
        assert result["consistent"] is True
        assert result["issues"] == []

    def test_tech_saas_no_anti_patterns_no_llm(self):
        """tech_saas has empty anti_patterns list; no LLM → rules default."""
        result = IndustryVerifier.verify_industry_consistency(
            "SaaS", "ARR增长30% NRR 120% 续约率95%"
        )
        # SaaS metrics are CORRECT for SaaS → consistent
        assert result["consistent"] is True
        assert result["method"] == "rules"

    # ── LLM fallback tests ──────────────────────────────────────────────

    def test_llm_detects_semantic_issue_when_rules_find_none(self):
        """LLM can catch issues that exact keyword anti-patterns miss."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "consistent": False,
            "issues": ["报告中使用了'客户流失率'，该指标不适用于汽车行业"],
        }, ensure_ascii=False)
        mock_llm.invoke.return_value = mock_response

        report = "600418 客户流失率上升至5% 市场份额下降"
        result = IndustryVerifier.verify_industry_consistency(
            "汽车制造", report, quick_llm=mock_llm,
        )

        assert result["consistent"] is False
        assert len(result["issues"]) >= 1
        assert result["method"] == "llm"
        assert result["severity"] == "warning"
        mock_llm.invoke.assert_called_once()

    def test_llm_confirms_consistency(self):
        """LLM can confirm report is consistent even for fuzzy cases."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "consistent": True,
            "issues": [],
        })
        mock_llm.invoke.return_value = mock_response

        result = IndustryVerifier.verify_industry_consistency(
            "汽车制造", "月度销量增长，产能利用率提升", quick_llm=mock_llm,
        )

        assert result["consistent"] is True
        assert result["issues"] == []
        assert result["method"] == "llm"
        mock_llm.invoke.assert_called_once()

    def test_llm_not_called_when_anti_patterns_found(self):
        """LLM is NOT invoked when rules already give definitive answer."""
        mock_llm = MagicMock()

        report = "600418 续约率下降 ARR不及预期"
        IndustryVerifier.verify_industry_consistency(
            "汽车制造", report, quick_llm=mock_llm,
        )

        mock_llm.invoke.assert_not_called()

    def test_llm_fallback_graceful_on_exception(self):
        """When LLM.invoke throws, degrade gracefully to consistent."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("API unavailable")

        result = IndustryVerifier.verify_industry_consistency(
            "汽车制造", "销量数据报告", quick_llm=mock_llm,
        )

        assert result["consistent"] is True
        assert result["issues"] == []
        assert result["method"] == "llm"  # Tried LLM path

    def test_llm_not_called_when_no_framework(self):
        """LLM not called when industry has no framework."""
        mock_llm = MagicMock()
        IndustryVerifier.verify_industry_consistency(
            "不存在的行业", "一些文本", quick_llm=mock_llm,
        )
        mock_llm.invoke.assert_not_called()
