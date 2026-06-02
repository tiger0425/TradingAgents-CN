"""Tests for IndustryClassifier service.

TDD: written BEFORE implementation to verify contract.
"""
from unittest.mock import patch

import pytest

from tradingagents.industry.classifier import IndustryClassifier, IndustryResult


class TestIndustryResult:
    """IndustryResult dataclass contract tests."""

    def test_defaults(self):
        """All fields should have sensible defaults."""
        result = IndustryResult()
        assert result.primary == ""
        assert result.secondary == ""
        assert result.confidence == 0.0
        assert result.source == ""

    def test_construction(self):
        """Fields should be settable via constructor."""
        result = IndustryResult(
            primary="汽车制造",
            secondary="载货车",
            confidence=0.95,
            source="a_stock_data",
        )
        assert result.primary == "汽车制造"
        assert result.secondary == "载货车"
        assert result.confidence == 0.95
        assert result.source == "a_stock_data"

    def test_is_dataclass(self):
        """IndustryResult should be a dataclass (like planner.schemas)."""
        import dataclasses
        assert dataclasses.is_dataclass(IndustryResult), (
            "IndustryResult must be a dataclass"
        )


class TestIndustryClassifierUnit:
    """IndustryClassifier unit tests with mocked get_industry()."""

    def test_classify_success(self):
        """Wraps a valid get_industry() result into IndustryResult."""
        with patch(
            "tradingagents.industry.classifier.get_industry",
            return_value="商用载货车",
        ):
            result = IndustryClassifier().classify("600418")

        assert result.primary == "商用载货车"
        assert result.secondary == ""
        assert result.confidence == 1.0
        assert result.source == "a_stock_data"

    def test_classify_with_subcategory_roman(self):
        """Splits Roman-numeral subcategories (e.g. 白酒Ⅱ → 白酒 / Ⅱ)."""
        with patch(
            "tradingagents.industry.classifier.get_industry",
            return_value="白酒Ⅱ",
        ):
            result = IndustryClassifier().classify("600519")

        assert result.primary == "白酒"
        assert result.secondary == "Ⅱ"
        assert result.confidence == 1.0
        assert result.source == "a_stock_data"

    def test_classify_unknown_returns_degraded(self):
        """When get_industry() returns '未知', return degraded result."""
        with patch(
            "tradingagents.industry.classifier.get_industry",
            return_value="未知",
        ):
            result = IndustryClassifier().classify("999999")

        assert result.primary == "未知"
        assert result.secondary == ""
        assert result.confidence == 0.0
        assert result.source == "fallback"

    def test_classify_exception_returns_degraded(self):
        """When get_industry() raises, return degraded result (no crash)."""
        with patch(
            "tradingagents.industry.classifier.get_industry",
            side_effect=RuntimeError("API unreachable"),
        ):
            result = IndustryClassifier().classify("999999")

        assert result.primary == "未知"
        assert result.secondary == ""
        assert result.confidence == 0.0
        assert result.source == "fallback"

    def test_classify_empty_string_returns_degraded(self):
        """Empty string from get_industry() should also degrade."""
        with patch(
            "tradingagents.industry.classifier.get_industry",
            return_value="",
        ):
            result = IndustryClassifier().classify("000001")

        assert result.primary == "未知"
        assert result.secondary == ""
        assert result.confidence == 0.0
        assert result.source == "fallback"

    def test_classify_none_returns_degraded(self):
        """None from get_industry() should also degrade."""
        with patch(
            "tradingagents.industry.classifier.get_industry",
            return_value=None,
        ):
            result = IndustryClassifier().classify("000001")

        assert result.primary == "未知"
        assert result.confidence == 0.0
        assert result.source == "fallback"


@pytest.mark.integration
class TestIndustryClassifierIntegration:
    """Real integration tests (require network / data source access)."""

    def test_classify_600418_contains_industry(self):
        """600418 (江淮汽车) should return primary containing 汽车 or 商用载货."""
        result = IndustryClassifier().classify("600418")
        assert result.primary, "primary should not be empty"
        assert "汽车" in result.primary or "商用载货" in result.primary, (
            f"Expected '汽车' or '商用载货' in primary, got: {result.primary}"
        )
        assert result.confidence > 0
        # Source should be meaningful even if it falls back
        assert result.source in ("a_stock_data", "fallback")

    @pytest.mark.slow
    def test_classify_999999_returns_unknown(self):
        """Non-existent code 999999 should degrade gracefully (no exception).

        NOTE: This test is slow because get_industry() tries all 3 fallback
        sources before returning '未知'. Unit tests verify the same behavior
        with mocked data.
        """
        result = IndustryClassifier().classify("999999")
        assert result.primary == "未知"
        assert result.confidence == 0.0
