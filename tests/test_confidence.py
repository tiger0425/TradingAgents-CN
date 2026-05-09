"""Tests for confidence tag computation — rule-based confidence system.

Tests verify CONFIRMED, SINGLE, CONFLICTING, STALE tag computation
and threshold filtering behaviour.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path

from tradingagents.graph.context_assembly import (
    ContextAssembler,
    CONFIDENCE_LEVELS,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_entry(
    idx: int,
    decision: str,
    date_str: str = None,
) -> dict:
    if date_str is None:
        date_str = (datetime.now() - timedelta(days=idx)).strftime("%Y-%m-%d")
    return {
        "id": f"entry_{idx}",
        "date": date_str,
        "ticker": "600519",
        "decision": decision,
        "type": "morning-scan",
        "rating": decision,
        "analysts": ["market"],
    }


def _make_assembler(tmp_path, tags_enabled=True):
    config = {
        "analysis_archive_dir": str(tmp_path / "archive"),
        "data_cache_dir": str(tmp_path / "cache"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "knowledge_token_budget": 25000,
        "confidence_tags_enabled": tags_enabled,
        "confidence_threshold_inject": "CONFLICTING",
    }
    return ContextAssembler(config)


# ============================================================================
# CONFIRMED tag
# ============================================================================


class TestConfirmedTag:
    def test_three_recent_same_direction_buy(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(5, "Buy"),
            _make_entry(10, "Buy"),
            _make_entry(15, "Buy"),
        ]
        tags = asm._compute_confidence("600519", entries)
        assert tags["overall"] == "CONFIRMED"
        assert tags["level"] == CONFIDENCE_LEVELS["CONFIRMED"]

    def test_three_recent_same_direction_sell(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(3, "Sell"),
            _make_entry(7, "Sell"),
            _make_entry(12, "Sell"),
        ]
        tags = asm._compute_confidence("600519", entries)
        assert tags["overall"] == "CONFIRMED"


# ============================================================================
# SINGLE tag
# ============================================================================


class TestSingleTag:
    def test_single_entry(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [_make_entry(5, "Buy")]
        tags = asm._compute_confidence("600519", entries)
        assert tags["overall"] == "SINGLE"
        assert tags["level"] == CONFIDENCE_LEVELS["SINGLE"]

    def test_empty_entries(self, tmp_path):
        asm = _make_assembler(tmp_path)
        tags = asm._compute_confidence("600519", [])
        assert tags["overall"] == "SINGLE"
        assert tags["signal_distribution"]["buy"] == 0
        assert tags["signal_distribution"]["sell"] == 0
        assert tags["signal_distribution"]["hold"] == 0


# ============================================================================
# CONFLICTING tag
# ============================================================================


class TestConflictingTag:
    def test_mixed_buy_sell_recent(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(5, "Buy"),
            _make_entry(10, "Sell"),
            _make_entry(15, "Buy"),
        ]
        tags = asm._compute_confidence("600519", entries)
        assert tags["overall"] == "CONFLICTING"
        assert tags["level"] == CONFIDENCE_LEVELS["CONFLICTING"]

    def test_buy_and_hold_not_conflicting(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(5, "Buy"),
            _make_entry(10, "Buy"),
            _make_entry(15, "Hold"),
        ]
        tags = asm._compute_confidence("600519", entries)
        # Hold does not create conflict, so >1 but <3 same direction → depends
        # With 2 Buy + 1 Hold, not CONFLICTING (no Sell/Underweight)
        assert tags["overall"] != "CONFLICTING"


# ============================================================================
# STALE tag
# ============================================================================


class TestStaleTag:
    def test_old_entries_stale(self, tmp_path):
        asm = _make_assembler(tmp_path)
        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        entries = [_make_entry(0, "Buy", date_str=old_date)]
        tags = asm._compute_confidence("600519", entries)
        assert tags["overall"] == "STALE"
        assert tags["level"] == CONFIDENCE_LEVELS["STALE"]

    def test_mixed_old_and_new(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(5, "Buy"),          # recent
            _make_entry(100, "Buy"),        # stale (>90d)
            _make_entry(120, "Sell"),       # stale (>90d)
        ]
        tags = asm._compute_confidence("600519", entries)
        # Only 1 recent entry → SINGLE (not STALE because there is a recent one)
        assert tags["overall"] == "SINGLE"


# ============================================================================
# Threshold filtering
# ============================================================================


class TestThresholdFiltering:
    def test_configured_threshold_respected(self, tmp_path):
        config = {
            "analysis_archive_dir": str(tmp_path / "archive"),
            "data_cache_dir": str(tmp_path / "cache"),
            "memory_log_path": str(tmp_path / "memory.md"),
            "confidence_tags_enabled": True,
            "confidence_threshold_inject": "CONFIRMED",
        }
        asm = ContextAssembler(config)
        # SINGLE is below CONFIRMED threshold
        tags = {"overall": "SINGLE", "level": CONFIDENCE_LEVELS["SINGLE"]}
        context = {"archived_analyses": [{"id": "test"}]}
        result = asm.filter_by_confidence(context, tags)
        assert result["archived_analyses"] == []

    def test_conflicting_at_threshold(self, tmp_path):
        config = {
            "analysis_archive_dir": str(tmp_path / "archive"),
            "data_cache_dir": str(tmp_path / "cache"),
            "memory_log_path": str(tmp_path / "memory.md"),
            "confidence_tags_enabled": True,
            "confidence_threshold_inject": "CONFLICTING",
        }
        asm = ContextAssembler(config)
        # CONFLICTING meets CONFLICTING threshold (equal)
        tags = {"overall": "CONFLICTING", "level": CONFIDENCE_LEVELS["CONFLICTING"]}
        context = {"archived_analyses": [{"id": "test"}]}
        result = asm.filter_by_confidence(context, tags)
        assert len(result["archived_analyses"]) == 1


# ============================================================================
# Label mapping
# ============================================================================


class TestLabels:
    def test_label_mapping(self, tmp_path):
        asm = _make_assembler(tmp_path)

        entries_3buy = [_make_entry(i, "Buy") for i in range(5, 35, 10)]
        tags = asm._compute_confidence("600519", entries_3buy)
        assert tags["label"] == "多次确认信号"

    def test_single_label(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [_make_entry(5, "Buy")]
        tags = asm._compute_confidence("600519", entries)
        assert tags["label"] == "单一分析记录"

    def test_conflicting_label(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(5, "Buy"),
            _make_entry(10, "Sell"),
        ]
        tags = asm._compute_confidence("600519", entries)
        assert tags["label"] == "信号冲突"


# ============================================================================
# Signal distribution
# ============================================================================


class TestSignalDistribution:
    def test_counts_by_decision(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [
            _make_entry(5, "Buy"),
            _make_entry(10, "Buy"),
            _make_entry(15, "Sell"),
            _make_entry(20, "Hold"),
        ]
        tags = asm._compute_confidence("600519", entries)
        dist = tags["signal_distribution"]
        assert dist["buy"] == 2
        assert dist["sell"] == 1
        assert dist["hold"] == 1

    def test_overweight_is_bullish(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [_make_entry(5, "Overweight")]
        tags = asm._compute_confidence("600519", entries)
        assert tags["signal_distribution"]["buy"] == 1
        assert tags["signal_distribution"]["sell"] == 0

    def test_underweight_is_bearish(self, tmp_path):
        asm = _make_assembler(tmp_path)
        entries = [_make_entry(5, "Underweight")]
        tags = asm._compute_confidence("600519", entries)
        assert tags["signal_distribution"]["buy"] == 0
        assert tags["signal_distribution"]["sell"] == 1
