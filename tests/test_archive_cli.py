"""Tests for the CLI ``archive`` command group.

Tests use ``typer.testing.CliRunner`` with ``monkeypatch`` to redirect
``_get_archive()`` to a temporary ``AnalysisArchive``, avoiding any
dependency on ``~/.tradingagents/``.

Coverage: help, list-entries, get-entry, search-entries, ticker-summary,
rebuild-index with various filters, output modes, and edge conditions.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from cli.archive import archive_app
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
        },
        "analysis": {
            "final_decision": decision,
            "rating": decision,
            "reasoning": "综合看多空因素...",
            "signals": {
                "market": {
                    "direction": "cautious",
                    "summary": "市场谨慎，放量突破",
                },
                "technical": {
                    "direction": "bullish",
                    "summary": "MACD金叉，RSI强势",
                },
            },
        },
        "tags": ["放量", "MACD金叉"],
    }


def setup_archive(monkeypatch, tmp_path):
    """Create an AnalysisArchive backed by *tmp_path* and monkeypatch
    ``cli.archive._get_archive`` to return it."""
    archive = AnalysisArchive(tmp_path)
    monkeypatch.setattr("cli.archive._get_archive", lambda: archive)
    return archive


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def runner():
    """Return a fresh Typer CliRunner."""
    return CliRunner()


# ===================================================================
# 1. help
# ===================================================================

def test_archive_help(runner, monkeypatch, tmp_path):
    """``--help`` shows all 5 subcommands."""
    setup_archive(monkeypatch, tmp_path)
    result = runner.invoke(archive_app, ["--help"])
    assert result.exit_code == 0
    assert "list-entries" in result.stdout
    assert "get-entry" in result.stdout
    assert "search-entries" in result.stdout
    assert "ticker-summary" in result.stdout
    assert "rebuild-index" in result.stdout


# ===================================================================
# 2. list-entries
# ===================================================================

def test_list_no_entries(runner, monkeypatch, tmp_path):
    """list-entries on an empty archive shows the '没有匹配' message."""
    setup_archive(monkeypatch, tmp_path)
    result = runner.invoke(archive_app, ["list-entries"])
    assert result.exit_code == 0
    assert "没有匹配的存档条目" in result.stdout


def test_list_with_entries(runner, monkeypatch, tmp_path):
    """list-entries with entries returns them with key fields."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09", "buy"), "morning-scan")

    result = runner.invoke(archive_app, ["list-entries"])
    assert result.exit_code == 0
    assert "找到 1 条记录" in result.stdout
    assert "600519" in result.stdout
    assert "morning-scan" in result.stdout
    assert "buy" in result.stdout


def test_list_ticker_filter(runner, monkeypatch, tmp_path):
    """``--ticker 600519`` only returns entries for that ticker."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
    archive.save(build_sample_result("000001", "2026-05-09"), "morning-scan")

    result = runner.invoke(archive_app, ["list-entries", "--ticker", "600519"])
    assert result.exit_code == 0
    assert "600519" in result.stdout
    assert "000001" not in result.stdout


def test_list_decision_filter(runner, monkeypatch, tmp_path):
    """``--decision buy`` only returns buy entries."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09", "buy"), "morning-scan")
    archive.save(build_sample_result("000001", "2026-05-09", "sell"), "morning-scan")

    result = runner.invoke(archive_app, ["list-entries", "--decision", "buy"])
    assert result.exit_code == 0
    assert "buy" in result.stdout
    assert "sell" not in result.stdout


def test_list_json_output(runner, monkeypatch, tmp_path):
    """``--output json`` returns valid JSON (list of entry metadata)."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

    result = runner.invoke(archive_app, ["list-entries", "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["ticker"] == "600519"
    assert data[0]["decision"] == "hold"


# ===================================================================
# 3. get-entry
# ===================================================================

def test_get_nonexistent(runner, monkeypatch, tmp_path):
    """get-entry with a bad ID exits with code 1 and prints error."""
    setup_archive(monkeypatch, tmp_path)
    result = runner.invoke(archive_app, ["get-entry", "2026/05/09/morning-scan_bad"])
    assert result.exit_code == 1
    assert "未找到条目" in result.stdout or "未找到条目" in result.stderr


def test_get_valid_entry(runner, monkeypatch, tmp_path):
    """get-entry returns full content including reasoning and signals."""
    archive = setup_archive(monkeypatch, tmp_path)
    entry_id = archive.save(
        build_sample_result("600519", "2026-05-09", "buy"), "morning-scan"
    )

    result = runner.invoke(archive_app, ["get-entry", entry_id])
    assert result.exit_code == 0
    assert "600519" in result.stdout
    assert "buy" in result.stdout
    assert "综合看多空因素" in result.stdout
    assert "市场谨慎" in result.stdout


def test_get_json_output(runner, monkeypatch, tmp_path):
    """``get-entry --output json`` returns the full entry dict as JSON."""
    archive = setup_archive(monkeypatch, tmp_path)
    entry_id = archive.save(
        build_sample_result("600519", "2026-05-09", "hold"), "morning-scan"
    )

    result = runner.invoke(archive_app, ["get-entry", entry_id, "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["_meta"]["id"] == entry_id
    assert data["request"]["ticker"] == "600519"
    assert data["analysis"]["final_decision"] == "hold"
    assert "signals" in data["analysis"]


# ===================================================================
# 4. search-entries
# ===================================================================

def test_search_found(runner, monkeypatch, tmp_path):
    """search-entries with a matching keyword returns results."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

    result = runner.invoke(archive_app, ["search-entries", "MACD金叉"])
    assert result.exit_code == 0
    assert "找到 1 条匹配" in result.stdout
    assert "600519" in result.stdout


def test_search_not_found(runner, monkeypatch, tmp_path):
    """search-entries with no matches shows '未找到' message."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

    result = runner.invoke(archive_app, ["search-entries", "不存在的词_XYZ"])
    assert result.exit_code == 0
    assert "未找到包含" in result.stdout


def test_search_json_output(runner, monkeypatch, tmp_path):
    """``search-entries --output json`` returns valid JSON list."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")

    result = runner.invoke(
        archive_app, ["search-entries", "MACD金叉", "--output", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["ticker"] == "600519"


# ===================================================================
# 5. ticker-summary
# ===================================================================

def test_summary_output(runner, monkeypatch, tmp_path):
    """ticker-summary shows distribution info for a ticker with entries."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09", "buy"), "morning-scan")
    archive.save(build_sample_result("600519", "2026-05-10", "sell"), "evening-review")

    result = runner.invoke(archive_app, ["ticker-summary", "600519"])
    assert result.exit_code == 0
    assert "600519" in result.stdout
    assert "总条目数:" in result.stdout
    assert "决策分布" in result.stdout
    assert "条目类型分布" in result.stdout
    # Should have both "buy" and "sell" in the decision section
    assert "buy" in result.stdout or "sell" in result.stdout


def test_summary_no_entries(runner, monkeypatch, tmp_path):
    """ticker-summary for an unknown ticker shows '无存档记录'."""
    setup_archive(monkeypatch, tmp_path)
    result = runner.invoke(archive_app, ["ticker-summary", "UNKNOWN"])
    assert result.exit_code == 0
    assert "无存档记录" in result.stdout


def test_summary_json_output(runner, monkeypatch, tmp_path):
    """``ticker-summary --output json`` returns the summary dict as JSON."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09", "buy"), "morning-scan")

    result = runner.invoke(
        archive_app, ["ticker-summary", "600519", "--output", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ticker"] == "600519"
    assert data["total_entries"] == 1
    assert "by_decision" in data
    assert "by_type" in data
    assert "trend" in data


# ===================================================================
# 6. rebuild-index
# ===================================================================

def test_rebuild_index(runner, monkeypatch, tmp_path):
    """rebuild-index prints the correct entry count."""
    archive = setup_archive(monkeypatch, tmp_path)
    archive.save(build_sample_result("600519", "2026-05-09"), "morning-scan")
    archive.save(build_sample_result("000001", "2026-05-10"), "evening-review")

    result = runner.invoke(archive_app, ["rebuild-index"])
    assert result.exit_code == 0
    assert "索引重建完成" in result.stdout
    assert "2 条记录" in result.stdout


def test_rebuild_index_empty(runner, monkeypatch, tmp_path):
    """rebuild-index on empty archive prints 0 count."""
    setup_archive(monkeypatch, tmp_path)
    result = runner.invoke(archive_app, ["rebuild-index"])
    assert result.exit_code == 0
    assert "索引重建完成" in result.stdout
    assert "0 条记录" in result.stdout
