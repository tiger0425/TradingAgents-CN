"""Tests for ContextAssembler — knowledge assembly node.

Tests verify assemble() returns correct structure, handles empty archives,
applies token budget, and correctly formats output for agent consumption.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timedelta

from tradingagents.graph.context_assembly import (
    ContextAssembler,
    _is_bullish,
    _is_bearish,
    _parse_date,
    _date_in_range,
    CONFIDENCE_LEVELS,
    TAG_HIERARCHY,
)
from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.agents.utils.memory import TradingMemoryLog


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def empty_config(tmp_path):
    return {
        "analysis_archive_dir": str(tmp_path / "archive"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "knowledge_token_budget": 25000,
        "confidence_tags_enabled": True,
        "confidence_threshold_inject": "CONFLICTING",
        "enable_context_assembly": True,
    }


@pytest.fixture
def assembler(empty_config):
    return ContextAssembler(empty_config)


@pytest.fixture
def seeded_archive(tmp_path):
    """Create an AnalysisArchive with sample entries."""
    archive_dir = tmp_path / "archive"
    archive = AnalysisArchive(str(archive_dir))

    base_date = datetime.now() - timedelta(days=5)
    for i in range(5):
        date = base_date - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        result = {
            "request": {"ticker": "600519", "date": date_str, "analysts": ["market", "news"]},
            "analysis": {"final_decision": "Buy" if i % 2 == 0 else "Hold", "rating": "Buy"},
            "tags": [],
        }
        archive.save(result, "morning-scan")

    # Add one Sell entry for mixed signals
    sell_date = base_date - timedelta(days=10)
    result_sell = {
        "request": {"ticker": "600519", "date": sell_date.strftime("%Y-%m-%d"), "analysts": ["technical"]},
        "analysis": {"final_decision": "Sell", "rating": "Sell"},
        "tags": [],
    }
    archive.save(result_sell, "morning-scan")

    return archive, archive_dir


# ============================================================================
# assemble() structure tests
# ============================================================================


class TestAssembleStructure:
    def test_returns_dict_with_expected_keys(self, assembler):
        result = assembler.assemble("600519", "2026-05-09")
        assert isinstance(result, dict)
        assert "archived_analyses" in result
        assert "past_decisions" in result
        assert "ticker_signals" in result
        assert "lessons" in result
        assert "cache_status" in result
        assert "_confidence_tags" in result
        assert "_confidence_metadata" in result

    def test_empty_archive_returns_empty_lists(self, assembler):
        result = assembler.assemble("000001", "2020-01-01")
        assert result["archived_analyses"] == []
        assert result["past_decisions"] == ""
        assert isinstance(result["ticker_signals"], dict)
        assert isinstance(result["lessons"], list)

    def test_confidence_metadata_populated(self, assembler):
        result = assembler.assemble("600519", "2026-05-09")
        meta = result["_confidence_metadata"]
        assert meta["ticker"] == "600519"
        assert meta["date"] == "2026-05-09"
        assert meta["market_type"] == "A_SHARE"
        assert meta["confidence_tags_enabled"] is True
        assert meta["budget_applied"] == 25000

    def test_confidence_tags_disabled_with_flag(self, empty_config):
        cfg = {**empty_config, "confidence_tags_enabled": False}
        asm = ContextAssembler(cfg)
        result = asm.assemble("600519", "2026-05-09")
        assert result["_confidence_tags"] == {}

    def test_signal_summary_returned(self, assembler):
        result = assembler.assemble("600519", "2026-05-09")
        signals = result["ticker_signals"]
        assert "ticker" in signals
        assert "period_days" in signals
        assert "by_decision" in signals
        assert "by_type" in signals
        assert "trend" in signals

    def test_cache_status_snapshot(self, assembler):
        result = assembler.assemble("600519", "2026-05-09")
        cache = result["cache_status"]
        assert "cache_dir" in cache
        assert "exists" in cache


# ============================================================================
# assemble() with seeded archive
# ============================================================================


class TestAssembleWithArchive:
    def test_assembles_archived_entries(self, empty_config, seeded_archive):
        archive, _ = seeded_archive
        asm = ContextAssembler(empty_config)
        with patch.object(asm, 'archive', archive):
            result = asm.assemble("600519", "2026-05-09")

        assert len(result["archived_analyses"]) > 0
        first = result["archived_analyses"][0]
        assert "id" in first
        assert "date" in first
        assert "decision" in first
        assert "ticker" in first

    def test_archived_entries_capped_at_5(self, empty_config, seeded_archive):
        archive, _ = seeded_archive
        asm = ContextAssembler(empty_config)
        with patch.object(asm, 'archive', archive):
            result = asm.assemble("600519", "2026-05-09")

        assert len(result["archived_analyses"]) <= 5


# ============================================================================
# Token budget tests
# ============================================================================


class TestTokenBudget:
    def test_no_truncation_when_under_budget(self, empty_config):
        cfg = {**empty_config, "knowledge_token_budget": 500000}
        asm = ContextAssembler(cfg)
        result = asm.assemble("600519", "2026-05-09")
        applied = result.get("_budget_applied", {})
        assert not applied.get("truncated", False)

    def test_truncation_when_over_budget(self, empty_config):
        cfg = {**empty_config, "knowledge_token_budget": 50}
        asm = ContextAssembler(cfg)
        result = asm.assemble("600519", "2026-05-09")
        applied = result.get("_budget_applied", {})
        assert applied.get("truncated", False) is True
        assert applied.get("after_tokens", 999) <= applied.get("before_tokens", 0)

    def test_budget_metadata_populated(self, empty_config):
        cfg = {**empty_config, "knowledge_token_budget": 10000}
        asm = ContextAssembler(cfg)
        result = asm.assemble("600519", "2026-05-09")
        meta = result.get("_budget_applied", {})
        assert meta.get("budget") == 10000
        assert "before_tokens" in meta
        assert "after_tokens" in meta

    def test_count_tokens_approximate(self):
        data = {"key": "hello world 你好世界" * 100}
        tokens = ContextAssembler._count_tokens(data)
        # Should be roughly len(serialized) // 4
        serialized = json.dumps(data, ensure_ascii=False, default=str)
        expected = max(1, len(serialized) // 4)
        assert tokens == expected


# ============================================================================
# Signal summary tests
# ============================================================================


class TestSignalSummary:
    def test_empty_ticker_returns_zero(self, assembler):
        signals = assembler._summarize_signals("NONEXISTENT_TICKER")
        assert signals["total_entries"] == 0
        assert signals["period_days"] == 30

    def test_custom_days_parameter(self, assembler):
        signals = assembler._summarize_signals("600519", days=7)
        assert signals["period_days"] == 7

    def test_signal_summary_has_expected_shape(self, assembler):
        signals = assembler._summarize_signals("600519")
        assert isinstance(signals["by_decision"], dict)
        assert isinstance(signals["by_type"], dict)
        assert isinstance(signals["trend"], list)


# ============================================================================
# Lessons extraction tests
# ============================================================================


class TestLessonsExtraction:
    def test_returns_list(self, assembler):
        lessons = assembler._extract_lessons()
        assert isinstance(lessons, list)

    def test_lessons_capped_at_10(self, assembler):
        lessons = assembler._extract_lessons()
        assert len(lessons) <= 10


# ============================================================================
# Confidence filter tests
# ============================================================================


class TestFilterByConfidence:
    def test_filters_below_threshold(self, empty_config):
        cfg = {**empty_config, "confidence_threshold_inject": "CONFIRMED"}
        asm = ContextAssembler(cfg)
        context = {"archived_analyses": [{"id": "test"}], "past_decisions": "test"}
        tags = {"overall": "SINGLE", "level": 3}

        filtered = asm.filter_by_confidence(context, tags)
        assert filtered["archived_analyses"] == []
        assert "_filtered_out_reason" in filtered

    def test_passes_above_threshold(self, empty_config):
        cfg = {**empty_config, "confidence_threshold_inject": "CONFLICTING"}
        asm = ContextAssembler(cfg)
        context = {"archived_analyses": [{"id": "test"}], "past_decisions": "test"}
        tags = {"overall": "CONFIRMED", "level": 4}

        filtered = asm.filter_by_confidence(context, tags)
        assert len(filtered["archived_analyses"]) == 1
        assert "_filtered_out_reason" not in filtered


# ============================================================================
# Module-level helpers
# ============================================================================


class TestModuleHelpers:
    def test_is_bullish_buy(self):
        assert _is_bullish({"decision": "Buy"}) is True

    def test_is_bullish_overweight(self):
        assert _is_bullish({"decision": "Overweight"}) is True

    def test_is_bullish_not_bullish(self):
        assert _is_bullish({"decision": "Sell"}) is False
        assert _is_bullish({"decision": "Hold"}) is False

    def test_is_bearish_sell(self):
        assert _is_bearish({"decision": "Sell"}) is True

    def test_is_bearish_underweight(self):
        assert _is_bearish({"decision": "Underweight"}) is True

    def test_is_bearish_not_bearish(self):
        assert _is_bearish({"decision": "Buy"}) is False

    def test_parse_date_valid(self):
        result = _parse_date("2026-05-09")
        assert result == datetime(2026, 5, 9)

    def test_parse_date_invalid(self):
        result = _parse_date("not-a-date")
        assert result == datetime.min

    def test_date_in_range(self):
        start = datetime(2026, 5, 1)
        end = datetime(2026, 5, 31)
        assert _date_in_range("2026-05-09", start, end) is True
        assert _date_in_range("2026-04-30", start, end) is False
        assert _date_in_range("invalid", start, end) is False

    def test_confidence_levels_hierarchy(self):
        assert CONFIDENCE_LEVELS["CONFIRMED"] > CONFIDENCE_LEVELS["SINGLE"]
        assert CONFIDENCE_LEVELS["SINGLE"] > CONFIDENCE_LEVELS["DERIVED"]
        assert CONFIDENCE_LEVELS["DERIVED"] > CONFIDENCE_LEVELS["CONFLICTING"]
        assert CONFIDENCE_LEVELS["CONFLICTING"] > CONFIDENCE_LEVELS["STALE"]

    def test_tag_hierarchy_order(self):
        assert TAG_HIERARCHY == [
            "CONFIRMED", "SINGLE", "DERIVED", "CONFLICTING", "STALE"
        ]
