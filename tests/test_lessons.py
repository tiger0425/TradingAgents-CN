"""Tests for WikiGenerator lessons extraction and deduplication.

Covers: _extract_all_lessons(), _deduplicate_lessons(),
_build_lessons_page(), edge cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.knowledge.wiki_generator import WikiGenerator
from tests.test_wiki import _build_result as _make_result


# ── Helpers ────────────────────────────────────────────────────


def _save(archive, result, entry_type="morning-scan"):
    return archive.save(result, entry_type)


def _days_ago(days):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def archive(tmp_path):
    return AnalysisArchive(str(tmp_path / "archive"))


@pytest.fixture
def wiki(tmp_path, archive):
    return WikiGenerator(archive, output_dir=str(tmp_path / "wiki"))


# ── Test _extract_all_lessons ──────────────────────────────────


class TestExtractAllLessons:
    def test_extracts_reasoning(self, wiki, archive):
        result = _make_result(
            ticker="600519", date="2026-05-09", decision="Buy"
        )
        _save(archive, result)
        entries = archive.list(limit=100)
        lessons = wiki._extract_all_lessons(entries)
        assert len(lessons) >= 1
        lesson = lessons[0]
        assert lesson["ticker"] == "600519"
        assert "Mock reasoning" in lesson["lesson"]

    def test_extracts_tags_when_no_reasoning(self, wiki, archive):
        result = {
            "request": {"ticker": "600519", "date": "2026-05-09", "analysts": []},
            "analysis": {"final_decision": "hold", "rating": "hold"},
            "tags": ["MACD金叉"],
        }
        _save(archive, result)
        entries = archive.list(limit=100)
        lessons = wiki._extract_all_lessons(entries)
        assert len(lessons) >= 1

    def test_empty_archive(self, wiki):
        lessons = wiki._extract_all_lessons([])
        assert lessons == []

    def test_skip_entries_without_reasoning_or_tags(self, wiki, archive):
        result = {
            "request": {"ticker": "000001", "date": "2026-05-09", "analysts": []},
            "analysis": {"final_decision": "hold", "rating": "hold"},
        }
        _save(archive, result)
        entries = archive.list(limit=100)
        lessons = wiki._extract_all_lessons(entries)
        assert len(lessons) == 0

    def test_sorts_by_date_desc(self, wiki, archive):
        for i, (d, dec) in enumerate([
            ("2026-05-07", "Buy"),
            ("2026-05-08", "Hold"),
            ("2026-05-09", "Sell"),
        ]):
            _save(archive, _make_result(ticker="600519", date=d, decision=dec))
        entries = archive.list(limit=100)
        lessons = wiki._extract_all_lessons(entries)
        if len(lessons) >= 2:
            assert lessons[0]["date"] >= lessons[-1]["date"]


# ── Test _deduplicate_lessons ──────────────────────────────────


class TestDeduplicateLessons:
    def test_dedup_same_ticker_within_7_days(self, wiki):
        lessons = [
            {"ticker": "600519", "date": _days_ago(1),
             "rating": "Buy", "lesson": "First lesson"},
            {"ticker": "600519", "date": _days_ago(3),
             "rating": "Buy", "lesson": "Second lesson < 7d"},
        ]
        result = wiki._deduplicate_lessons(lessons)
        assert len(result) == 1

    def test_keep_same_ticker_beyond_7_days(self, wiki):
        lessons = [
            {"ticker": "600519", "date": _days_ago(8),
             "rating": "Buy", "lesson": "Old lesson"},
            {"ticker": "600519", "date": _days_ago(1),
             "rating": "Buy", "lesson": "Recent lesson"},
        ]
        result = wiki._deduplicate_lessons(lessons)
        assert len(result) == 2

    def test_keep_different_tickers(self, wiki):
        lessons = [
            {"ticker": "600519", "date": _days_ago(1),
             "rating": "Buy", "lesson": "茅台 lesson"},
            {"ticker": "000001", "date": _days_ago(2),
             "rating": "Sell", "lesson": "平安 lesson"},
        ]
        result = wiki._deduplicate_lessons(lessons)
        assert len(result) == 2

    def test_empty_lessons(self, wiki):
        result = wiki._deduplicate_lessons([])
        assert result == []

    def test_keep_lessons_without_ticker(self, wiki):
        lessons = [
            {"ticker": "", "date": _days_ago(1),
             "rating": "Buy", "lesson": "No ticker"},
            {"ticker": "", "date": _days_ago(2),
             "rating": "Hold", "lesson": "No ticker too"},
        ]
        result = wiki._deduplicate_lessons(lessons)
        assert len(result) == 2


# ── Test _build_lessons_page ───────────────────────────────────


class TestBuildLessonsPage:
    def test_empty_lessons(self, wiki):
        page = wiki._build_lessons_page([])
        assert "暂无经验教训记录" in page

    def test_single_lesson(self, wiki):
        lessons = [
            {"ticker": "600519", "date": "2026-05-09",
             "rating": "Buy", "lesson": "Test lesson content."},
        ]
        page = wiki._build_lessons_page(lessons)
        assert "Test lesson content" in page
        assert "600519" in page

    def test_multiple_lessons(self, wiki):
        lessons = [
            {"ticker": "600519", "date": "2026-05-09",
             "rating": "Buy", "lesson": "First."},
            {"ticker": "000001", "date": "2026-05-08",
             "rating": "Sell", "lesson": "Second."},
        ]
        page = wiki._build_lessons_page(lessons)
        assert "First." in page
        assert "Second." in page

    def test_lesson_truncation(self, wiki):
        long_text = "A" * 500
        lessons = [
            {"ticker": "600519", "date": "2026-05-09",
             "rating": "Buy", "lesson": long_text},
        ]
        page = wiki._build_lessons_page(lessons)
        assert "..." in page
        assert len(page) < len(long_text) + 200

    def test_rating_displayed(self, wiki):
        lessons = [
            {"ticker": "600519", "date": "2026-05-09",
             "rating": "Overweight", "lesson": "Lesson."},
        ]
        page = wiki._build_lessons_page(lessons)
        assert "Overweight" in page

    def test_back_link(self, wiki):
        page = wiki._build_lessons_page([])
        assert "[← 返回索引](index.md)" in page
