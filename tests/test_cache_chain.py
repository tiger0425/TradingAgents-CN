"""Tests for the triple cache check chain in propagate().

Covers Level 1 (same-ticker-same-day skip), Level 2 (incremental
mode activation), post-analysis archive save, config defaults, and
backward compatibility.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.graph.trading_graph import TradingAgentsGraph


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def base_config(tmp_path):
    """Minimal config that avoids network/LLM calls during tests."""
    return {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-4o",
        "quick_think_llm": "gpt-4o-mini",
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "data_cache_dir": str(tmp_path / "cache"),
        "results_dir": str(tmp_path / "results"),
        "analysis_archive_dir": str(tmp_path / "archive"),
        "memory_log_path": str(tmp_path / "memory.md"),
        "market_type": "A_SHARE",
        "benchmark_name": "\u6caa\u6df1300",
        "benchmark_ticker": "000300",
        "enable_context_assembly": False,
        "checkpoint_enabled": False,
        "skip_if_analyzed_today": False,
        "incremental_window_days": 0,
        "enable_archive_first_cache": True,
    }


@pytest.fixture
def sample_archive_entry(tmp_path):
    """Pre-populate archive with a sample batch entry and return (entry_id, content)."""
    archive_dir = tmp_path / "archive"
    archive = AnalysisArchive(str(archive_dir))

    entry_date = "2026-05-09"
    ticker = "600519"
    entry_id = AnalysisArchive._build_entry_id(entry_date, "batch", ticker)

    result = {
        "request": {
            "ticker": ticker,
            "date": entry_date,
            "analysts": ["market", "technical"],
            "llm_provider": "openai",
            "config_snapshot": {"market_type": "A_SHARE"},
        },
        "analysis": {
            "signals": {
                "market": {"direction": "bullish", "summary": "\u5e02\u573a\u4e0a\u6da8"},
            },
            "final_decision": "Buy",
            "rating": "Buy",
            "reasoning": "\u7efc\u5408\u5206\u6790\u770b\u591a",
        },
        "tags": ["\u653e\u91cf", "MACD\u91d1\u53c9"],
    }
    saved_id = archive.save(result, "batch")
    return entry_id, result


@pytest.fixture
def mock_trading_graph_components():
    """Patch out heavy initialization so TradingAgentsGraph can be constructed."""
    with patch(
        "tradingagents.graph.trading_graph.create_llm_client"
    ) as mock_llm, patch(
        "tradingagents.graph.trading_graph.TradingMemoryLog"
    ) as mock_memory, patch(
        "tradingagents.graph.trading_graph.PositionStateManager"
    ) as mock_pos, patch(
        "tradingagents.graph.trading_graph.set_config"
    ) as mock_set, patch.object(
        TradingAgentsGraph, "_create_tool_nodes", return_value={"market": MagicMock()}
    ), patch(
        "tradingagents.graph.trading_graph.GraphSetup"
    ) as mock_graph_setup, patch(
        "tradingagents.graph.trading_graph.Propagator"
    ) as mock_propagator, patch(
        "tradingagents.graph.trading_graph.Reflector"
    ), patch(
        "tradingagents.graph.trading_graph.SignalProcessor"
    ):
        mock_llm.return_value.get_llm.return_value = MagicMock()
        mock_memory.return_value.get_past_context.return_value = ""
        mock_memory.return_value.get_pending_entries.return_value = []
        mock_memory.return_value.store_decision.return_value = None
        mock_memory.return_value.batch_update_with_outcomes.return_value = None
        mock_pos.return_value.load.return_value = None
        mock_graph_setup.return_value.setup_graph.return_value = MagicMock()
        mock_propagator.return_value.create_initial_state.return_value = {}
        mock_propagator.return_value.get_graph_args.return_value = {}
        yield


# ============================================================================
# Test Level 1: skip_if_analyzed_today
# ============================================================================


class TestLevel1Cache:

    def test_skip_if_analyzed_today_disabled(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        config = {**base_config}
        config["skip_if_analyzed_today"] = False
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph.propagate("600519", "2026-05-09")
        graph._run_graph.assert_called_once()

    def test_skip_if_analyzed_today_enabled_no_cache(self, base_config, mock_trading_graph_components, tmp_path):
        config = {**base_config}
        config["skip_if_analyzed_today"] = True
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph.propagate("000001", "2026-05-09")
        graph._run_graph.assert_called_once()

    def test_skip_if_analyzed_today_cache_hit(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        entry_id, entry = sample_archive_entry
        config = {**base_config}
        config["skip_if_analyzed_today"] = True
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock()

        state, decision = graph.propagate("600519", "2026-05-09")
        graph._run_graph.assert_not_called()
        assert decision == "Buy"
        assert state["final_trade_decision"] == "Buy"
        assert state["_cached"] is True
        assert state["company_of_interest"] == "600519"

    def test_skip_if_analyzed_today_wrong_ticker(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        config = {**base_config}
        config["skip_if_analyzed_today"] = True
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph.propagate("000001", "2026-05-09")
        graph._run_graph.assert_called_once()

    def test_skip_when_decision_in_top_level(self, base_config, mock_trading_graph_components, tmp_path):
        archive_dir = tmp_path / "archive"
        archive = AnalysisArchive(str(archive_dir))

        entry_date = "2026-05-09"
        entry_id = AnalysisArchive._build_entry_id(entry_date, "batch", "600519")

        result = {
            "request": {"ticker": "600519", "date": entry_date},
            "analysis": {"final_decision": "Sell"},
        }
        archive.save(result, "batch")

        config = {**base_config}
        config["skip_if_analyzed_today"] = True
        config["analysis_archive_dir"] = str(archive_dir)

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock()

        state, decision = graph.propagate("600519", "2026-05-09")
        assert decision == "Sell"
        assert state["_cached"] is True


# ============================================================================
# Test Level 2: incremental_window_days
# ============================================================================


class TestLevel2Cache:

    def test_incremental_window_disabled(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        config = {**base_config}
        config["incremental_window_days"] = 0
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph.propagate("600519", "2026-05-09")
        assert getattr(graph, "_incremental_mode", False) is False

    def test_incremental_window_enabled_recent_found(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        config = {**base_config}
        config["incremental_window_days"] = 90
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph.propagate("600519", "2026-05-01")
        assert graph._incremental_mode is True
        assert len(graph._recent_analyses) == 1

    def test_incremental_window_no_recent(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        config = {**base_config}
        config["incremental_window_days"] = 3
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph.propagate("600519", "2027-01-01")
        assert getattr(graph, "_incremental_mode", False) is False

    def test_incremental_mode_flags_reset(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        config = {**base_config}
        config["incremental_window_days"] = 0
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        graph._incremental_mode = True
        graph._recent_analyses = [{"id": "test"}]

        graph.propagate("600519", "2026-05-09")
        assert graph._incremental_mode is False
        assert graph._recent_analyses == []


# ============================================================================
# Test Post-Analysis Archive Save
# ============================================================================


class TestPostAnalysisArchive:

    def test_archive_saved_after_propagate(self, base_config, mock_trading_graph_components, tmp_path):
        config = {**base_config}
        config["enable_archive_first_cache"] = True
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Overweight"}, "Overweight"
        ))

        graph.propagate("600519", "2026-05-09")

        archive = AnalysisArchive(str(tmp_path / "archive"))
        entry_id = AnalysisArchive._build_entry_id("2026-05-09", "batch", "600519")
        cached = archive.get(entry_id)
        assert cached is not None
        assert cached["analysis"]["final_decision"] == "Overweight"

    def test_archive_save_handles_exception(self, base_config, mock_trading_graph_components, tmp_path):
        config = {**base_config}
        config["enable_archive_first_cache"] = True
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        with patch("cli.archive.save_to_archive", side_effect=OSError("disk full")):
            result = graph.propagate("600519", "2026-05-09")
            assert result[1] == "Hold"

    def test_archive_save_disabled(self, base_config, mock_trading_graph_components, tmp_path):
        config = {**base_config}
        config["enable_archive_first_cache"] = False
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Sell"}, "Sell"
        ))

        graph.propagate("000001", "2026-05-09")

        archive = AnalysisArchive(str(tmp_path / "archive"))
        entry_id = AnalysisArchive._build_entry_id("2026-05-09", "batch", "000001")
        cached = archive.get(entry_id)
        assert cached is None


# ============================================================================
# Test Config Defaults
# ============================================================================


class TestConfigDefaults:

    def test_config_keys_exist(self):
        from tradingagents.default_config import DEFAULT_CONFIG
        assert "skip_if_analyzed_today" in DEFAULT_CONFIG
        assert "incremental_window_days" in DEFAULT_CONFIG
        assert "enable_archive_first_cache" in DEFAULT_CONFIG
        assert "analysis_archive_dir" in DEFAULT_CONFIG

    def test_defaults_are_safe(self):
        from tradingagents.default_config import DEFAULT_CONFIG
        assert DEFAULT_CONFIG["skip_if_analyzed_today"] is False
        assert DEFAULT_CONFIG["incremental_window_days"] == 0
        assert DEFAULT_CONFIG["enable_archive_first_cache"] is True


# ============================================================================
# Test Backward Compatibility
# ============================================================================


class TestBackwardCompat:

    def test_defaults_match_existing_behavior(self, base_config, mock_trading_graph_components, tmp_path):
        config = {**base_config}
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Hold"}, "Hold"
        ))

        state, decision = graph.propagate("600519", "2026-05-09")
        assert isinstance(state, dict)
        assert isinstance(decision, str)
        assert "final_trade_decision" in state

    def test_propagate_return_type_unchanged(self, base_config, mock_trading_graph_components, tmp_path):
        config = {**base_config}
        config["skip_if_analyzed_today"] = False
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock(return_value=(
            {"final_trade_decision": "Buy"}, "Buy"
        ))

        result = graph.propagate("600519", "2026-05-09")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], dict)
        assert isinstance(result[1], str)

    def test_level1_return_type_matches_propagate(self, base_config, mock_trading_graph_components, tmp_path, sample_archive_entry):
        entry_id, entry = sample_archive_entry
        config = {**base_config}
        config["skip_if_analyzed_today"] = True
        config["analysis_archive_dir"] = str(tmp_path / "archive")

        graph = TradingAgentsGraph(config=config)
        graph._run_graph = MagicMock()

        result = graph.propagate("600519", "2026-05-09")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], dict)
        assert "final_trade_decision" in result[0]
        assert isinstance(result[1], str)
