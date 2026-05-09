"""Tests for WikiGenerator — wiki page generation from analysis archive.

Covers: _build_index, _build_ticker_page, generate(), incremental_update,
confidence computation, signal distribution, edge cases.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.knowledge.wiki_generator import WikiGenerator


# ── Helpers ────────────────────────────────────────────────────

def _build_result(ticker="600519", date="2026-05-09", decision="hold"):
    return {
        "request": {
            "ticker": ticker,
            "date": date,
            "analysts": ["market", "technical"],
        },
        "analysis": {
            "final_decision": decision,
            "rating": decision,
            "reasoning": f"Mock reasoning for {ticker} on {date}.",
        },
        "tags": ["放量突破"],
    }


def _seed_archive(archive, entries_data):
    for e in entries_data:
        r = _build_result(**e)
        archive.save(r, entry_type=e.get("type", "morning-scan"))


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def archive(tmp_path):
    return AnalysisArchive(str(tmp_path / "archive"))


@pytest.fixture
def seeded_archive(tmp_path):
    a = AnalysisArchive(str(tmp_path / "archive"))
    base = datetime.now() - timedelta(days=2)
    for i in range(5):
        d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        dec = "Buy" if i % 2 == 0 else "Hold"
        a.save(_build_result(ticker="600519", date=d, decision=dec), "morning-scan")
    return a


@pytest.fixture
def multi_ticker_archive(tmp_path):
    a = AnalysisArchive(str(tmp_path / "archive"))
    entries_data = [
        {"ticker": "600519", "date": "2026-05-09", "decision": "Buy"},
        {"ticker": "600519", "date": "2026-05-08", "decision": "Hold"},
        {"ticker": "600519", "date": "2026-05-07", "decision": "Buy"},
        {"ticker": "000001", "date": "2026-05-09", "decision": "Sell"},
        {"ticker": "000001", "date": "2026-05-08", "decision": "Hold"},
        {"ticker": "000858", "date": "2026-05-09", "decision": "Buy"},
    ]
    _seed_archive(a, entries_data)
    return a


@pytest.fixture
def wiki(tmp_path, archive):
    return WikiGenerator(archive, output_dir=str(tmp_path / "wiki"))


@pytest.fixture
def wiki_seeded(tmp_path, multi_ticker_archive):
    return WikiGenerator(multi_ticker_archive, output_dir=str(tmp_path / "wiki"))


# ── Test _build_index ──────────────────────────────────────────


class TestBuildIndex:
    def test_empty_archive(self, wiki):
        result = wiki._build_index([])
        assert "分析知识库导航" in result
        assert "0 条分析记录" in result
        assert "股票分析索引" in result

    def test_single_ticker(self, wiki_seeded):
        entries = wiki_seeded.archive.list(limit=100)
        result = wiki_seeded._build_index(entries)
        assert "600519" in result
        assert "000001" in result
        assert "000858" in result

    def test_table_format(self, wiki_seeded):
        entries = wiki_seeded.archive.list(limit=100)
        result = wiki_seeded._build_index(entries)
        assert "| Ticker | 名称 | 总分析次数 | 最近分析 | 当前信号 | 置信度 |" in result

    def test_confidence_tag_present(self, wiki_seeded):
        entries = wiki_seeded.archive.list(limit=100)
        result = wiki_seeded._build_index(entries)
        assert "CONFIRMED" in result or "SINGLE" in result or "STALE" in result

    def test_known_ticker_name(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        entries = archive.list(limit=100)
        result = wiki._build_index(entries)
        assert "贵州茅台" in result

    def test_unknown_ticker_falls_back(self, wiki, archive):
        archive.save(
            _build_result(ticker="999999", date="2026-05-09", decision="Hold"),
            "morning-scan",
        )
        entries = archive.list(limit=100)
        result = wiki._build_index(entries)
        assert "999999" in result

    def test_sort_by_count_desc(self, wiki_seeded):
        entries = wiki_seeded.archive.list(limit=100)
        result = wiki_seeded._build_index(entries)
        idx_519 = result.find("600519")
        idx_001 = result.find("000001")
        assert idx_519 < idx_001  # 600519 has more entries

    def test_available_commands(self, wiki_seeded):
        entries = wiki_seeded.archive.list(limit=100)
        result = wiki_seeded._build_index(entries)
        assert "tradingagents wiki show" in result
        assert "tradingagents wiki generate" in result


# ── Test _build_ticker_page ────────────────────────────────────


class TestBuildTickerPage:
    def test_basic_structure(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        entries = archive.list(ticker="600519")
        result = wiki._build_ticker_page("600519", entries)
        assert "# 600519" in result
        assert "信号时间线" in result
        assert "信号分布" in result

    def test_signal_timeline_table(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        entries = archive.list(ticker="600519")
        result = wiki._build_ticker_page("600519", entries)
        assert "| 日期 | 决策 | 评级 | 类型 |" in result
        assert "2026-05-09" in result
        assert "Buy" in result

    def test_confidence_summary(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        entries = archive.list(ticker="600519")
        result = wiki._build_ticker_page("600519", entries)
        assert "当前置信度" in result

    def test_signal_distribution(self, wiki_seeded):
        entries = wiki_seeded.archive.list(ticker="600519")
        result = wiki_seeded._build_ticker_page("600519", entries)
        assert "Buy:" in result
        assert "Sell:" in result
        assert "Hold:" in result

    def test_recent_5_entries(self, wiki_seeded):
        entries = wiki_seeded.archive.list(ticker="600519")
        result = wiki_seeded._build_ticker_page("600519", entries)
        assert "最近 5 条分析" in result

    def test_back_link(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        entries = archive.list(ticker="600519")
        result = wiki._build_ticker_page("600519", entries)
        assert "[← 返回索引](index.md)" in result


# ── Test generate() ────────────────────────────────────────────


class TestGenerate:
    def test_creates_index_file(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        index_path = wiki.generate()
        assert Path(index_path).exists()

    def test_creates_ticker_page(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        wiki.generate()
        ticker_page = Path(wiki.output_dir) / "600519.md"
        assert ticker_page.exists()

    def test_creates_lessons_page(self, wiki, archive):
        archive.save(
            _build_result(ticker="600519", date="2026-05-09", decision="Buy"),
            "morning-scan",
        )
        wiki.generate()
        lessons_page = Path(wiki.output_dir) / "lessons.md"
        assert lessons_page.exists()

    def test_empty_archive_graceful(self, wiki):
        index_path = wiki.generate()
        assert Path(index_path).exists()
        content = Path(index_path).read_text()
        assert "0 条分析记录" in content

    def test_single_ticker_generate(self, wiki_seeded):
        index_path = wiki_seeded.generate(ticker="600519")
        assert Path(index_path).exists()
        ticker_page = Path(wiki_seeded.output_dir) / "600519.md"
        assert ticker_page.exists()

    def test_returns_index_path(self, wiki):
        index_path = wiki.generate()
        assert index_path.endswith("index.md")


# ── Test incremental_update ────────────────────────────────────


class TestIncrementalUpdate:
    def test_no_new_entries(self, wiki):
        wiki.incremental_update([])

    def test_new_ticker_entry(self, wiki_seeded):
        new_entries = [
            {"ticker": "600519", "date": "2026-05-10", "decision": "Sell",
             "rating": "Sell", "type": "batch", "id": "2026/05/10/batch_600519",
             "analysts": [], "tags": []}
        ]
        wiki_seeded.incremental_update(new_entries)
        ticker_page = Path(wiki_seeded.output_dir) / "600519.md"
        assert ticker_page.exists()

    def test_regenerates_index(self, wiki_seeded):
        index_before = Path(wiki_seeded.output_dir) / "index.md"
        if index_before.exists():
            index_before.unlink()
        new_entries = [
            {"ticker": "600519", "date": "2026-05-10", "decision": "Buy",
             "rating": "Buy", "type": "batch", "id": "2026/05/10/batch_600519",
             "analysts": [], "tags": []}
        ]
        wiki_seeded.incremental_update(new_entries)
        assert index_before.exists() or (Path(wiki_seeded.output_dir) / "index.md").exists()


# ── Test confidence computation ────────────────────────────────


class TestConfidenceComputation:
    def test_empty_entries(self, wiki):
        tag = wiki._compute_confidence_tag("NONE", [])
        assert tag == "NONE"

    def test_single_entry(self, wiki):
        entries = [_build_result(ticker="600519", date="2026-05-09", decision="Buy")]
        entries = [_make_meta(entries[0], "id1")]
        tag = wiki._compute_confidence_tag("600519", entries)
        assert tag == "SINGLE"

    def test_confirmed_buy(self, wiki):
        base = datetime.now()
        entries = []
        for i in range(3):
            d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
            entries.append(_make_meta(
                _build_result(ticker="600519", date=d, decision="Buy"),
                f"id{i}",
            ))
        tag = wiki._compute_confidence_tag("600519", entries)
        assert "CONFIRMED" in tag

    def test_conflicting(self, wiki):
        now = datetime.now()
        entries = [
            _make_meta(_build_result(ticker="600519", date=now.strftime("%Y-%m-%d"),
                                     decision="Buy"), "id0"),
            _make_meta(_build_result(ticker="600519", date=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
                                     decision="Sell"), "id1"),
        ]
        tag = wiki._compute_confidence_tag("600519", entries)
        assert tag == "CONFLICTING"

    def test_stale(self, wiki):
        old = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        entry = _make_meta(
            _build_result(ticker="600519", date=old, decision="Buy"),
            "old_id",
        )
        tag = wiki._compute_confidence_tag("600519", [entry])
        assert tag == "STALE"

    def test_signal_distribution(self, wiki):
        entries = [
            _make_meta(_build_result(ticker="600519", decision="Buy"), "a"),
            _make_meta(_build_result(ticker="600519", decision="Sell"), "b"),
            _make_meta(_build_result(ticker="600519", decision="Hold"), "c"),
        ]
        dist = wiki._compute_signal_distribution(entries)
        assert dist == {"buy": 1, "sell": 1, "hold": 1}


# ── Helpers ────────────────────────────────────────────────────


def _make_meta(result, entry_id):
    return AnalysisArchive._extract_meta(entry_id, result)
