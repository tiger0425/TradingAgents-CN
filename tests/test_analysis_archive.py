"""Tests for AnalysisArchive — save, get, list, search, summary, delete, rebuild_index.

Coverage: basic CRUD, index integrity (root/month/day), edge conditions
(no date, no ticker, empty queries, overwrites), and multi-entry scenarios.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from tradingagents.analysis_archive import AnalysisArchive


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def build_sample_result(
    ticker: str = "600519",
    date: str = "2026-05-09",
    decision: str = "hold",
) -> dict:
    """Build a minimal but realistic analysis result dict for tests."""
    return {
        "request": {
            "ticker": ticker,
            "date": date,
            "analysts": ["market", "technical"],
            "llm_provider": "openai",
            "config_snapshot": {"market_type": "A_SHARE"},
        },
        "analysis": {
            "signals": {
                "market": {
                    "direction": "cautious",
                    "summary": "市场谨慎",
                    "details": "沪深300缩量",
                },
                "technical": {
                    "direction": "bullish",
                    "summary": "MACD金叉",
                    "details": "日线级别金叉",
                },
            },
            "final_decision": decision,
            "rating": decision,
            "reasoning": "综合看多空因素...",
        },
        "tags": ["放量", "MACD金叉"],
    }


# ===================================================================
# A. Basic Operations
# ===================================================================

class TestBasicOperations:

    def test_save_returns_entry_id(self, tmp_path):
        """save returns the expected entry ID format."""
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09")
        entry_id = archive.save(result, "morning-scan")
        assert entry_id == "2026/05/09/morning-scan_600519"

    def test_save_and_get(self, tmp_path):
        """save then get returns identical data (with _meta added)."""
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09", decision="buy")
        entry_id = archive.save(result, "morning-scan")
        loaded = archive.get(entry_id)
        assert loaded is not None
        assert loaded["analysis"]["final_decision"] == "buy"
        assert loaded["request"]["ticker"] == "600519"
        assert loaded["_meta"]["id"] == entry_id
        assert loaded["_meta"]["source_command"] == "morning-scan"
        assert loaded["_meta"]["cli_version"] == "0.2.5"

    def test_get_nonexistent(self, tmp_path):
        """get returns None for a non-existent entry ID."""
        archive = AnalysisArchive(tmp_path)
        assert archive.get("2026/05/09/morning-scan_nonexistent") is None

    def test_list_empty(self, tmp_path):
        """list returns an empty list on a fresh archive."""
        archive = AnalysisArchive(tmp_path)
        assert archive.list() == []

    def test_list_all(self, tmp_path):
        """list with no filters returns all entries."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        entries = archive.list()
        assert len(entries) == 1
        assert entries[0]["ticker"] == "600519"
        assert entries[0]["decision"] == "hold"

    def test_list_ticker_filter(self, tmp_path):
        """list filters by ticker correctly."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-09"), "morning-scan")

        filtered = archive.list(ticker="600519")
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "600519"

        filtered2 = archive.list(ticker="000001")
        assert len(filtered2) == 1
        assert filtered2[0]["ticker"] == "000001"

    def test_list_decision_filter(self, tmp_path):
        """list filters by decision case-insensitively."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09", decision="buy"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-09", decision="sell"), "morning-scan")

        buys = archive.list(decision="buy")
        assert len(buys) == 1
        assert buys[0]["decision"] == "buy"

        sells = archive.list(decision="SELL")
        assert len(sells) == 1
        assert sells[0]["decision"] == "sell"

    def test_list_entry_type_filter(self, tmp_path):
        """list filters by entry type."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-09"), "evening-review")

        morning = archive.list(entry_type="morning-scan")
        assert len(morning) == 1
        assert morning[0]["type"] == "morning-scan"

        evening = archive.list(entry_type="evening-review")
        assert len(evening) == 1
        assert evening[0]["type"] == "evening-review"

    def test_list_date_range(self, tmp_path):
        """list respects date_from and date_to filters."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-01"), "morning-scan")
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("600519", "2026-05-15"), "morning-scan")

        from_09 = archive.list(date_from="2026-05-09")
        assert len(from_09) == 2

        to_09 = archive.list(date_to="2026-05-09")
        assert len(to_09) == 2

        in_range = archive.list(date_from="2026-05-05", date_to="2026-05-10")
        assert len(in_range) == 1

    def test_list_limit(self, tmp_path):
        """list respects the limit parameter."""
        archive = AnalysisArchive(tmp_path)
        for i in range(5):
            archive.save(build_sample_result(f"6005{i:02d}", "2026-05-09"), "morning-scan")

        limited = archive.list(limit=3)
        assert len(limited) == 3

    def test_search_text(self, tmp_path):
        """search finds text within entry content."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        results = archive.search("MACD金叉")
        assert len(results) == 1
        assert results[0]["ticker"] == "600519"

    def test_search_nonexistent(self, tmp_path):
        """search returns empty list for non-matching text."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        results = archive.search("NOT_FOUND_TEXT_XYZ123")
        assert results == []

    def test_search_limit(self, tmp_path):
        """search respects the limit parameter."""
        archive = AnalysisArchive(tmp_path)
        for i in range(5):
            result = build_sample_result("600519", f"2026-05-{i + 1:02d}")
            result["analysis"]["reasoning"] = f"MACD金叉_信号第{i}条"
            archive.save(result, "morning-scan")

        results = archive.search("MACD金叉", limit=3)
        assert len(results) == 3

    def test_summary_counts(self, tmp_path):
        """summary returns correct by_decision and by_type distributions."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09", decision="buy"), "morning-scan")
        archive.save(build_sample_result("600519", "2026-05-10", decision="sell"), "evening-review")
        archive.save(build_sample_result("600519", "2026-05-11", decision="buy"), "morning-scan")

        s = archive.summary("600519")
        assert s["ticker"] == "600519"
        assert s["total_entries"] == 3
        assert s["by_decision"] == {"buy": 2, "sell": 1}
        assert s["by_type"] == {"morning-scan": 2, "evening-review": 1}
        assert len(s["trend"]) == 3

    def test_summary_period(self, tmp_path):
        """summary respects the days parameter and returns period_days."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        s = archive.summary("600519", days=30)
        assert s["period_days"] == 30

    def test_delete_existing(self, tmp_path):
        """delete returns True for an existing entry."""
        archive = AnalysisArchive(tmp_path)
        entry_id = archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        assert archive.delete(entry_id) is True

    def test_delete_nonexistent(self, tmp_path):
        """delete returns False for a non-existent entry."""
        archive = AnalysisArchive(tmp_path)
        assert archive.delete("2026/05/09/morning-scan_nonexistent") is False

    def test_delete_removes_file(self, tmp_path):
        """after delete, get returns None for the deleted entry."""
        archive = AnalysisArchive(tmp_path)
        entry_id = archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        assert archive.get(entry_id) is not None
        archive.delete(entry_id)
        assert archive.get(entry_id) is None

    def test_rebuild_index_empty(self, tmp_path):
        """rebuild_index on empty archive returns 0."""
        archive = AnalysisArchive(tmp_path)
        assert archive.rebuild_index() == 0

    def test_rebuild_index_after_save(self, tmp_path):
        """rebuild_index returns the correct count after saving entries."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-10"), "evening-review")
        assert archive.rebuild_index() == 2


# ===================================================================
# B. Index Integrity
# ===================================================================

class TestIndexIntegrity:

    def test_index_after_save(self, tmp_path):
        """Root index correctly reflects entries after a save."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        root_idx = archive._load_index(archive.archive_dir / "index.json")
        assert root_idx["total_entries"] == 1
        assert "600519" in root_idx["by_ticker"]
        assert len(root_idx["by_ticker"]["600519"]) == 1

    def test_index_after_delete(self, tmp_path):
        """Root index is cleared after the only entry is deleted."""
        archive = AnalysisArchive(tmp_path)
        entry_id = archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.delete(entry_id)

        root_idx = archive._load_index(archive.archive_dir / "index.json")
        assert root_idx["total_entries"] == 0
        assert root_idx["by_ticker"] == {}

    def test_index_after_rebuild(self, tmp_path):
        """rebuild_index recovers from a corrupted root index."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        idx_path = archive.archive_dir / "index.json"
        idx_path.write_text("this is not valid json ===", encoding="utf-8")

        count = archive.rebuild_index()
        assert count == 1

        root_idx = archive._load_index(idx_path)
        assert root_idx["total_entries"] == 1

    def test_index_month_level(self, tmp_path):
        """Month-level index.json exists and contains the correct entry."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        month_idx = archive._load_index(archive.archive_dir / "2026" / "05" / "index.json")
        assert month_idx["total_entries"] == 1
        assert month_idx["entries"][0]["ticker"] == "600519"

    def test_index_day_level(self, tmp_path):
        """Day-level index.json exists and contains the correct entry."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        day_idx = archive._load_index(archive.archive_dir / "2026" / "05" / "09" / "index.json")
        assert day_idx["total_entries"] == 1
        assert day_idx["entries"][0]["ticker"] == "600519"

    def test_index_by_ticker_lookup(self, tmp_path):
        """The by_ticker lookup map correctly maps tickers to entry IDs."""
        archive = AnalysisArchive(tmp_path)
        e1 = archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        e2 = archive.save(build_sample_result("000001", "2026-05-09"), "morning-scan")

        root_idx = archive._load_index(archive.archive_dir / "index.json")
        assert "600519" in root_idx["by_ticker"]
        assert "000001" in root_idx["by_ticker"]
        assert root_idx["by_ticker"]["600519"][0] == e1
        assert root_idx["by_ticker"]["000001"][0] == e2

    def test_index_by_decision_lookup(self, tmp_path):
        """The by_decision lookup map correctly groups by decision."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09", decision="buy"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-09", decision="sell"), "morning-scan")

        root_idx = archive._load_index(archive.archive_dir / "index.json")
        assert "buy" in root_idx["by_decision"]
        assert "sell" in root_idx["by_decision"]
        assert len(root_idx["by_decision"]["buy"]) == 1
        assert len(root_idx["by_decision"]["sell"]) == 1


# ===================================================================
# C. Edge Conditions
# ===================================================================

class TestEdgeConditions:

    def test_save_no_date_defaults_to_today(self, tmp_path):
        """save uses today's date when result has no date."""
        archive = AnalysisArchive(tmp_path)
        result = {
            "request": {"ticker": "600519", "analysts": ["market"]},
            "analysis": {"final_decision": "hold", "rating": "hold", "reasoning": "无日期测试"},
            "tags": [],
        }
        entry_id = archive.save(result, "morning-scan")

        today = datetime.now().strftime("%Y/%m/%d")
        assert entry_id.startswith(today)
        assert entry_id.endswith("morning-scan_600519")

    def test_save_no_ticker_defaults_to_unknown(self, tmp_path):
        """save uses 'unknown' when result has no ticker."""
        archive = AnalysisArchive(tmp_path)
        result = {
            "request": {"date": "2026-05-09", "analysts": ["market"]},
            "analysis": {"final_decision": "hold", "rating": "hold", "reasoning": "无股票测试"},
            "tags": [],
        }
        entry_id = archive.save(result, "morning-scan")
        assert "unknown" in entry_id
        assert entry_id.endswith("morning-scan_unknown")

    def test_empty_search_query(self, tmp_path):
        """An empty search query matches all entries (empty string in substring)."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-09"), "morning-scan")

        results = archive.search("")
        assert len(results) == 2

    def test_list_invalid_ticker_returns_empty(self, tmp_path):
        """list with a non-existent ticker returns []."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        assert archive.list(ticker="NOEXIST") == []

    def test_summary_no_entries(self, tmp_path):
        """summary for a ticker with no entries returns zero-filled result."""
        archive = AnalysisArchive(tmp_path)
        s = archive.summary("UNKNOWN")
        assert s["ticker"] == "UNKNOWN"
        assert s["total_entries"] == 0
        assert s["by_decision"] == {}
        assert s["by_type"] == {}
        assert s["trend"] == []

    def test_multi_ticker_list(self, tmp_path):
        """list correctly filters among mixed tickers."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-09"), "morning-scan")
        archive.save(build_sample_result("300750", "2026-05-09"), "morning-scan")

        assert len(archive.list()) == 3
        filtered = archive.list(ticker="600519")
        assert len(filtered) == 1
        assert filtered[0]["ticker"] == "600519"

    def test_save_overwrite(self, tmp_path):
        """Saving with the same ticker/type/date overwrites the previous entry."""
        archive = AnalysisArchive(tmp_path)
        result1 = build_sample_result("600519", "2026-05-09", decision="buy")
        entry_id = archive.save(result1, "morning-scan")

        result2 = build_sample_result("600519", "2026-05-09", decision="sell")
        result2["analysis"]["reasoning"] = "覆盖后的理由"
        entry_id2 = archive.save(result2, "morning-scan")

        assert entry_id == entry_id2
        loaded = archive.get(entry_id)
        assert loaded["analysis"]["final_decision"] == "sell"
        assert loaded["analysis"]["reasoning"] == "覆盖后的理由"
        assert len(archive.list()) == 1

    def test_save_no_meta_preexisting(self, tmp_path):
        """save correctly adds _meta even when result has no _meta at all."""
        archive = AnalysisArchive(tmp_path)
        result = {
            "request": {"ticker": "600519", "date": "2026-05-09", "analysts": []},
            "analysis": {"final_decision": "hold", "rating": "hold", "reasoning": "测试"},
            "tags": [],
        }
        entry_id = archive.save(result, "morning-scan")
        loaded = archive.get(entry_id)
        assert "_meta" in loaded
        assert loaded["_meta"]["id"] == entry_id
        assert loaded["_meta"]["source_command"] == "morning-scan"

    def test_get_corrupted_json(self, tmp_path):
        """get returns None when the entry file contains corrupt JSON."""
        archive = AnalysisArchive(tmp_path)
        entry_id = "2026/05/09/morning-scan_600519"
        entry_path = archive._entry_path(entry_id)
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text("not valid {{{ json", encoding="utf-8")

        assert archive.get(entry_id) is None

    def test_search_case_insensitive(self, tmp_path):
        """search is case-insensitive."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

        results_lower = archive.search("macd金叉")
        results_upper = archive.search("MACD金叉")
        assert len(results_lower) == len(results_upper) == 1

    def test_date_from_id_handles_short_id(self, tmp_path):
        """_date_from_id returns empty string for malformed entry IDs."""
        assert AnalysisArchive._date_from_id("short") == ""
        assert AnalysisArchive._date_from_id("2026/05") == ""

    def test_build_entry_id_dash_to_slash(self, tmp_path):
        """_build_entry_id converts dashes to slashes in the date."""
        eid = AnalysisArchive._build_entry_id("2026-05-09", "morning-scan", "600519")
        assert eid == "2026/05/09/morning-scan_600519"

    def test_date_from_id_roundtrip(self, tmp_path):
        """_date_from_id reverses _build_entry_id for valid dates."""
        eid = AnalysisArchive._build_entry_id("2026-12-31", "evening-review", "000001")
        assert AnalysisArchive._date_from_id(eid) == "2026-12-31"


# ===================================================================
# D. Multi-entry Scenarios
# ===================================================================

class TestMultiEntryScenarios:

    def test_multiple_entries(self, tmp_path):
        """Saving 5 entries with different tickers; list returns all 5."""
        archive = AnalysisArchive(tmp_path)
        tickers = ["600519", "000001", "300750", "000858", "002594"]
        for t in tickers:
            archive.save(build_sample_result(t, "2026-05-09"), "morning-scan")

        entries = archive.list()
        assert len(entries) == 5
        returned_tickers = {e["ticker"] for e in entries}
        assert returned_tickers == set(tickers)

    def test_summary_mixed_decisions(self, tmp_path):
        """summary correctly tallies mixed buy/sell/hold decisions."""
        archive = AnalysisArchive(tmp_path)
        decisions = ["buy", "buy", "sell", "hold", "buy", "sell", "hold", "hold"]
        for i, d in enumerate(decisions):
            archive.save(
                build_sample_result("600519", f"2026-05-{i + 1:02d}", decision=d),
                "morning-scan",
            )

        s = archive.summary("600519", days=365)
        assert s["total_entries"] == 8
        assert s["by_decision"]["buy"] == 3
        assert s["by_decision"]["sell"] == 2
        assert s["by_decision"]["hold"] == 3
        assert len(s["trend"]) == 8

    def test_search_across_multiple(self, tmp_path):
        """search locates a specific entry among many."""
        archive = AnalysisArchive(tmp_path)
        for i in range(5):
            result = build_sample_result("600519", f"2026-05-{i + 1:02d}")
            result["analysis"]["reasoning"] = f"理由_{i} MACD金叉"
            archive.save(result, "morning-scan")

        special = build_sample_result("000001", "2026-05-09")
        special["analysis"]["reasoning"] = "搜索目标词_UNIQUE_XYZ"
        archive.save(special, "morning-scan")

        results = archive.search("搜索目标词_UNIQUE_XYZ")
        assert len(results) == 1
        assert results[0]["ticker"] == "000001"

    def test_list_sorted_by_date_descending(self, tmp_path):
        """list returns entries sorted by date descending."""
        archive = AnalysisArchive(tmp_path)
        dates = ["2026-05-01", "2026-05-05", "2026-05-03", "2026-05-09", "2026-05-02"]
        for i, d in enumerate(dates):
            archive.save(build_sample_result(f"6005{i:02d}", d), "morning-scan")

        entries = archive.list()
        returned_dates = [e["date"] for e in entries]
        assert returned_dates == sorted(dates, reverse=True)

    def test_save_entry_creates_json_file(self, tmp_path):
        """save actually creates a .json file on disk."""
        archive = AnalysisArchive(tmp_path)
        entry_id = archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        entry_path = archive._entry_path(entry_id)
        assert entry_path.exists()
        assert entry_path.suffix == ".json"

    def test_save_and_list_with_full_filters(self, tmp_path):
        """list with all filter params combined returns correct subset."""
        archive = AnalysisArchive(tmp_path)
        archive.save(build_sample_result("600519", "2026-05-09", "buy"), "morning-scan")
        archive.save(build_sample_result("600519", "2026-05-10", "sell"), "evening-review")
        archive.save(build_sample_result("000001", "2026-05-09", "buy"), "morning-scan")
        archive.save(build_sample_result("000001", "2026-05-11", "hold"), "morning-scan")

        results = archive.list(
            ticker="600519",
            decision="buy",
            entry_type="morning-scan",
        )
        assert len(results) == 1
        assert results[0]["ticker"] == "600519"
        assert results[0]["decision"] == "buy"
        assert results[0]["type"] == "morning-scan"

    def test_list_all_params_return_metadata_not_full_content(self, tmp_path):
        """list returns index metadata dicts, not the full JSON content."""
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09")
        archive.save(result, "morning-scan")

        entries = archive.list()
        assert len(entries) == 1
        meta = entries[0]
        assert "id" in meta
        assert "date" in meta
        assert "type" in meta
        assert "ticker" in meta
        assert "decision" in meta
        assert "rating" in meta
        assert "analysts" in meta
        assert "tags" in meta
        assert "signals" not in meta
        assert "reasoning" not in meta


# ===================================================================
# E. Constructor and _meta edge cases
# ===================================================================

class TestConstructorAndMeta:

    def test_constructor_creates_archive_dir(self, tmp_path):
        """Constructor creates the archive directory if it doesn't exist."""
        archive_path = tmp_path / "nested" / "archive"
        assert not archive_path.exists()
        AnalysisArchive(archive_path)
        assert archive_path.exists()

    def test_constructor_with_string_path(self, tmp_path):
        """Constructor accepts a string path."""
        archive_path = tmp_path / "string_path"
        archive = AnalysisArchive(str(archive_path))
        assert archive.archive_dir == archive_path

    def test_save_preserves_tags(self, tmp_path):
        """save preserves tags from the original result."""
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09")
        result["tags"] = ["放量", "MACD金叉", "突破均线"]
        entry_id = archive.save(result, "morning-scan")
        loaded = archive.get(entry_id)
        assert loaded["tags"] == ["放量", "MACD金叉", "突破均线"]

    def test_save_preserves_config_snapshot(self, tmp_path):
        """save preserves nested config data."""
        archive = AnalysisArchive(tmp_path)
        result = build_sample_result("600519", "2026-05-09")
        entry_id = archive.save(result, "morning-scan")
        loaded = archive.get(entry_id)
        assert loaded["request"]["config_snapshot"] == {"market_type": "A_SHARE"}

    def test_delete_updates_by_decision_lookup(self, tmp_path):
        """After delete, the by_decision lookup no longer references the entry."""
        archive = AnalysisArchive(tmp_path)
        entry_id = archive.save(build_sample_result("600519", "2026-05-09", "buy"), "morning-scan")
        archive.delete(entry_id)

        root_idx = archive._load_index(archive.archive_dir / "index.json")
        assert root_idx["by_decision"] == {}

    def test_save_empty_analysts(self, tmp_path):
        """save handles empty analysts list gracefully."""
        archive = AnalysisArchive(tmp_path)
        result = {
            "request": {"ticker": "600519", "date": "2026-05-09", "analysts": []},
            "analysis": {"final_decision": "hold", "rating": "hold", "reasoning": "无分析师"},
            "tags": [],
        }
        entry_id = archive.save(result, "morning-scan")
        loaded = archive.get(entry_id)
        assert loaded["request"]["analysts"] == []

    def test_rebuild_after_delete_cleans_index(self, tmp_path):
        """rebuild_index after delete gives correct count and clean indexes."""
        archive = AnalysisArchive(tmp_path)
        entry_id = archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
        archive.delete(entry_id)

        count = archive.rebuild_index()
        assert count == 0

        root_idx = archive._load_index(archive.archive_dir / "index.json")
        assert root_idx["total_entries"] == 0
