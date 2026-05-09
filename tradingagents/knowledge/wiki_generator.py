"""Wiki navigation generator for analysis archive.

Produces agent-crawlable Markdown index files from analysis archive entries.
A lightweight RAG alternative inspired by graphify --wiki mode.

Products:
- wiki/index.md              — Full index: all tickers with analysis overview
- wiki/{ticker}.md           — Ticker detail page: signal history, confidence
- wiki/patterns/{name}.md    — Recurring market pattern pages
- wiki/lessons.md            — Cross-ticker lessons page
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.graph.context_assembly import CONFIDENCE_LEVELS

logger = logging.getLogger(__name__)


class WikiGenerator:
    """Wiki navigation generator.

    Produces agent-crawlable Markdown index files from analysis archive entries.

    Products:
    - wiki/index.md              — Full index: all tickers with analysis overview
    - wiki/{ticker}.md           — Ticker detail page: signal history, confidence
    - wiki/lessons.md            — Cross-ticker lessons page
    """

    def __init__(
        self,
        archive: AnalysisArchive,
        output_dir: str | Path = "~/.tradingagents/wiki/",
    ):
        """Initialize the Wiki generator.

        Args:
            archive: AnalysisArchive instance for reading entries.
            output_dir: Output directory for wiki Markdown files.
        """
        self.archive = archive
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ==================================================================
    # Public API
    # ==================================================================

    def generate(self, ticker: Optional[str] = None) -> str:
        """Generate complete Wiki. Returns index.md path.

        If ticker is specified, only generates that ticker's page
        (incremental update). Otherwise generates everything.

        Args:
            ticker: Optional ticker to generate/update a single page for.

        Returns:
            Path to the generated index.md file.
        """
        # Get all entries from archive
        all_entries = self.archive.list(limit=10000)

        if ticker:
            # Single ticker update
            ticker_entries = [e for e in all_entries if e.get("ticker") == ticker]
            if ticker_entries:
                self._write_page(
                    self.output_dir / f"{ticker}.md",
                    self._build_ticker_page(ticker, ticker_entries),
                )
            # Also rebuild index
            self._write_page(
                self.output_dir / "index.md",
                self._build_index(all_entries),
            )
            return str(self.output_dir / "index.md")

        # Full generation
        # 1. Build index page
        index_content = self._build_index(all_entries)
        self._write_page(self.output_dir / "index.md", index_content)

        # 2. Build ticker pages
        tickers = self._unique_tickers(all_entries)
        for tk in tickers:
            tk_entries = [e for e in all_entries if e.get("ticker") == tk]
            page = self._build_ticker_page(tk, tk_entries)
            self._write_page(self.output_dir / f"{tk}.md", page)

        # 3. Build lessons page
        lessons = self._extract_all_lessons(all_entries)
        deduped = self._deduplicate_lessons(lessons)
        lessons_content = self._build_lessons_page(deduped)
        self._write_page(self.output_dir / "lessons.md", lessons_content)

        logger.info(
            "Wiki generated: %d tickers, %d lessons → %s",
            len(tickers),
            len(deduped),
            self.output_dir,
        )

        return str(self.output_dir / "index.md")

    def incremental_update(self, new_entries: List[dict]) -> None:
        """Incremental update: only regenerate pages that have new entries.

        Compares new entry timestamps with existing pages and only rebuilds
        pages where new data is available.

        Args:
            new_entries: List of new entry metadata dicts from AnalysisArchive.
        """
        affected_tickers: set[str] = set()
        for e in new_entries:
            ticker = e.get("ticker", "")
            if ticker:
                affected_tickers.add(ticker)

        if not affected_tickers:
            logger.debug("incremental_update: no new entries to process")
            return

        # Get fresh list of all entries
        all_entries = self.archive.list(limit=10000)

        # Regenerate affected ticker pages
        for tk in affected_tickers:
            tk_entries = [e for e in all_entries if e.get("ticker") == tk]
            page = self._build_ticker_page(tk, tk_entries)
            self._write_page(self.output_dir / f"{tk}.md", page)

        # Always regenerate index page
        self._write_page(
            self.output_dir / "index.md",
            self._build_index(all_entries),
        )

        # Regenerate lessons if relevant
        lessons = self._extract_all_lessons(all_entries)
        deduped = self._deduplicate_lessons(lessons[:50])
        self._write_page(
            self.output_dir / "lessons.md",
            self._build_lessons_page(deduped),
        )

        logger.info(
            "Wiki incremental update: %d tickers affected",
            len(affected_tickers),
        )

    # ==================================================================
    # Page builders
    # ==================================================================

    def _build_index(self, entries: List[dict]) -> str:
        """Build top-level index page. Agent reads this to know full knowledge base.

        Args:
            entries: All entry metadata dicts from the archive.

        Returns:
            Markdown string for index.md.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Group by ticker
        by_ticker: Dict[str, List[dict]] = {}
        for e in entries:
            ticker = e.get("ticker", "")
            if ticker:
                by_ticker.setdefault(ticker, []).append(e)

        # Sort tickers by entry count descending
        sorted_tickers = sorted(
            by_ticker.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        lines = [
            "# 分析知识库导航",
            "",
            f"> 自动生成于 {now}",
            f"> 总计 {len(entries)} 条分析记录，覆盖 {len(sorted_tickers)} 只股票",
            "",
            "## 股票分析索引",
            "",
            "| Ticker | 名称 | 总分析次数 | 最近分析 | 当前信号 | 置信度 |",
            "|--------|------|-----------|---------|---------|-------|",
        ]

        for ticker, tk_entries in sorted_tickers:
            count = len(tk_entries)
            # Find latest date
            dates = sorted(
                [e.get("date", "") for e in tk_entries],
                reverse=True,
            )
            last_date = dates[0] if dates else "—"

            # Find current signal (most recent decision)
            tk_sorted = sorted(
                tk_entries, key=lambda e: e.get("date", ""), reverse=True
            )
            decision = tk_sorted[0].get("decision", "Hold") if tk_sorted else "Hold"

            # Compute confidence
            confidence = self._compute_confidence_tag(ticker, tk_entries)

            # Ticker name — use first available name info
            name = self._get_ticker_name(ticker, tk_entries)

            lines.append(
                f"| {ticker} | {name} | {count} | {last_date} "
                f"| {decision} | {confidence} |"
            )

        lines.append("")

        # Pattern section (simple grouping by tags)
        patterns = self._extract_patterns(entries)
        if patterns:
            lines.append("## 反复出现的市场模式")
            lines.append("")
            for pattern_name, pattern_count in sorted(
                patterns.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                lines.append(f"- [{pattern_name}](patterns/{pattern_name}.md) ({pattern_count} 次)")
            lines.append("")

        # Available commands
        lines.extend([
            "## 可用命令",
            "",
            "- `tradingagents wiki show <TICKER>` — 查看 ticker 详情",
            "- `tradingagents wiki list` — 列出所有 wiki 页面",
            "- `tradingagents wiki generate` — 重新生成全部 wiki",
            "- `tradingagents archive search \"关键词\"` — 全文搜索",
            "",
        ])

        return "\n".join(lines)

    def _build_ticker_page(self, ticker: str, entries: List[dict]) -> str:
        """Build ticker detail page with signal distribution and timeline.

        Args:
            ticker: Stock ticker symbol.
            entries: All entry metadata for this ticker.

        Returns:
            Markdown string for {ticker}.md.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        name = self._get_ticker_name(ticker, entries)

        lines = [
            f"# {ticker} — {name}",
            "",
            f"> 自动生成于 {now}",
            f"> 共 {len(entries)} 条分析记录",
            "",
        ]

        # Signal timeline
        lines.append("## 信号时间线")
        lines.append("")
        lines.append("| 日期 | 决策 | 评级 | 类型 |")
        lines.append("|------|------|------|------|")

        sorted_entries = sorted(entries, key=lambda e: e.get("date", ""), reverse=True)
        for e in sorted_entries[:30]:  # Cap at 30 most recent
            date = e.get("date", "—")
            decision = e.get("decision", "—")
            rating = e.get("rating", "—")
            entry_type = e.get("type", "—")
            lines.append(f"| {date} | {decision} | {rating} | {entry_type} |")

        lines.append("")

        # Confidence summary
        confidence = self._compute_confidence_tag(ticker, entries)
        signal_dist = self._compute_signal_distribution(entries)

        lines.append("## 信号分布")
        lines.append("")
        lines.append(f"- **当前置信度**: {confidence}")
        lines.append(
            f"- Buy: {signal_dist.get('buy', 0)} | "
            f"Sell: {signal_dist.get('sell', 0)} | "
            f"Hold: {signal_dist.get('hold', 0)}"
        )
        lines.append("")

        # Recent decisions
        recent = sorted_entries[:5]
        if recent:
            lines.append("## 最近 5 条分析")
            lines.append("")
            for e in recent:
                date = e.get("date", "—")
                decision = e.get("decision", "—")
                rating = e.get("rating", "—")
                eid = e.get("id", "")
                lines.append(f"- **{date}** — {decision} ({rating}) `{eid}`")
            lines.append("")

        # Link back
        lines.extend([
            "---",
            "",
            f"[← 返回索引](index.md) | [经验教训](lessons.md)",
            "",
        ])

        return "\n".join(lines)

    def _build_lessons_page(self, lessons: List[dict]) -> str:
        """Build cross-ticker lessons page.

        Args:
            lessons: List of lesson dicts with keys: ticker, date, rating, lesson.

        Returns:
            Markdown string for lessons.md.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            "# 跨股票经验教训",
            "",
            f"> 自动生成于 {now}",
            f"> 共 {len(lessons)} 条可复用洞察",
            "",
        ]

        if not lessons:
            lines.append("*暂无经验教训记录。随着分析的积累，跨股票的可复用模式将在此处展示。*")
            lines.append("")
            lines.append("[← 返回索引](index.md)")
            return "\n".join(lines)

        lines.append("## 经验列表（按时间倒序）")
        lines.append("")

        for lesson in lessons:
            ticker = lesson.get("ticker", "")
            date = lesson.get("date", "")
            rating = lesson.get("rating", "")
            text = lesson.get("lesson", "") or lesson.get("reflection_summary", "")

            # Truncate long lessons
            if len(text) > 300:
                text = text[:300] + "..."

            lines.append(f"### {date} — {ticker}")
            lines.append(f"*评级: {rating}*")
            lines.append("")
            lines.append(f"> {text}")
            lines.append("")

        lines.append("[← 返回索引](index.md)")
        return "\n".join(lines)

    # ==================================================================
    # Confidence computation
    # ==================================================================

    def _compute_confidence_tag(self, ticker: str, entries: List[dict]) -> str:
        """Compute a simplified confidence tag for wiki display.

        Rules (simplified from ContextAssembler):
        - CONFIRMED: 3+ same-direction signals in last 30 days
        - SINGLE: only 1 analysis
        - CONFLICTING: mixed buy/sell signals in last 30 days
        - STALE: newest analysis > 90 days ago

        Args:
            ticker: Stock ticker (unused, for interface consistency).
            entries: List of entry metadata dicts.

        Returns:
            Confidence tag string (e.g., "CONFIRMED", "SINGLE").
        """
        if not entries:
            return "NONE"

        now = datetime.now()
        cutoff_30d = now - timedelta(days=30)
        cutoff_90d = now - timedelta(days=90)

        # Parse dates
        entry_dates = []
        for e in entries:
            date_str = e.get("date", "")
            try:
                entry_dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
            except (ValueError, TypeError):
                entry_dates.append(now)

        # Recent entries within 30 days
        recent = [
            e
            for e, d in zip(entries, entry_dates)
            if d >= cutoff_30d
        ]

        # Count signal directions
        buy_count = sum(
            1 for e in recent
            if "buy" in (e.get("decision", "") or "").lower()
            or "overweight" in (e.get("decision", "") or "").lower()
        )
        sell_count = sum(
            1 for e in recent
            if "sell" in (e.get("decision", "") or "").lower()
            or "underweight" in (e.get("decision", "") or "").lower()
        )

        newest_date = max(entry_dates) if entry_dates else datetime.min

        if len(entries) == 1:
            if newest_date < cutoff_90d:
                return "STALE"
            return "SINGLE"
        elif buy_count > 0 and sell_count > 0:
            return "CONFLICTING"
        elif buy_count >= 3 or sell_count >= 3:
            direction = "Buy" if buy_count >= 3 else "Sell"
            return f"CONFIRMED ({direction})"
        elif newest_date < cutoff_90d:
            return "STALE"
        else:
            return "SINGLE"

    def _compute_signal_distribution(self, entries: List[dict]) -> dict:
        """Compute signal distribution counts.

        Returns dict with keys: buy, sell, hold.
        """
        dist = {"buy": 0, "sell": 0, "hold": 0}
        for e in entries:
            decision = (e.get("decision", "") or "").lower()
            if "buy" in decision or "overweight" in decision:
                dist["buy"] += 1
            elif "sell" in decision or "underweight" in decision:
                dist["sell"] += 1
            else:
                dist["hold"] += 1
        return dist

    # ==================================================================
    # Lessons extraction
    # ==================================================================

    def _extract_all_lessons(self, entries: List[dict]) -> List[dict]:
        """Extract lessons from analysis archive entries and memory log reflections.

        Tries to read full entry content for reflection/lesson data. Falls back
        to metadata-only when reading fails.

        Args:
            entries: Entry metadata list.

        Returns:
            List of lesson dicts with keys: ticker, date, rating, lesson.
        """
        lessons: List[dict] = []

        for e in entries:
            entry_id = e.get("id", "")
            ticker = e.get("ticker", "")
            date = e.get("date", "")
            rating = e.get("rating", "")

            # Try to read full content for lessons/reflections
            try:
                full = self.archive.get(entry_id)
                if full:
                    # Check for analysis reasoning
                    analysis = full.get("analysis", {})
                    reasoning = analysis.get("reasoning", "")
                    if reasoning and len(reasoning) > 20:
                        lessons.append({
                            "ticker": ticker,
                            "date": date,
                            "rating": rating,
                            "lesson": reasoning,
                        })
                        continue

                    # Check for tags (cross-ticker patterns)
                    tags = full.get("tags", [])
                    if tags:
                        lessons.append({
                            "ticker": ticker,
                            "date": date,
                            "rating": rating,
                            "lesson": f"关键标签: {', '.join(tags[:5])}",
                        })
            except (json.JSONDecodeError, OSError):
                pass

        # Sort most recent first
        lessons.sort(key=lambda x: x.get("date", ""), reverse=True)
        return lessons

    def _deduplicate_lessons(self, lessons: List[dict]) -> List[dict]:
        """Remove duplicate lessons for same ticker within 7 days.

        Args:
            lessons: List of lesson dicts, sorted by date descending.

        Returns:
            Deduplicated list.
        """
        seen: Dict[str, str] = {}  # ticker → latest_date_str
        deduped: List[dict] = []

        for lesson in lessons:
            ticker = lesson.get("ticker", "")
            date = lesson.get("date", "")

            if not ticker or not date:
                deduped.append(lesson)
                continue

            if ticker in seen:
                try:
                    last_dt = datetime.strptime(seen[ticker], "%Y-%m-%d")
                    curr_dt = datetime.strptime(date, "%Y-%m-%d")
                    if abs((last_dt - curr_dt).days) < 7:
                        continue
                except (ValueError, TypeError):
                    pass

            seen[ticker] = date
            deduped.append(lesson)

        return deduped

    # ==================================================================
    # Patterns extraction
    # ==================================================================

    def _extract_patterns(self, entries: List[dict]) -> Dict[str, int]:
        """Extract recurring patterns from entry tags.

        Args:
            entries: All entry metadata.

        Returns:
            Dict mapping pattern name → occurrence count.
        """
        patterns: Dict[str, int] = {}
        for e in entries:
            # Try loading tags from full entry
            try:
                full = self.archive.get(e.get("id", ""))
                if full:
                    tags = full.get("tags", [])
                    for tag in tags:
                        tag_clean = str(tag).strip()
                        if tag_clean:
                            patterns[tag_clean] = patterns.get(tag_clean, 0) + 1
            except (json.JSONDecodeError, OSError):
                pass
        return patterns

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _unique_tickers(entries: List[dict]) -> List[str]:
        """Get unique ticker symbols sorted by name/frequency."""
        tickers: Dict[str, int] = {}
        for e in entries:
            tk = e.get("ticker", "")
            if tk:
                tickers[tk] = tickers.get(tk, 0) + 1
        return sorted(tickers, key=lambda t: tickers[t], reverse=True)

    @staticmethod
    def _get_ticker_name(ticker: str, entries: List[dict]) -> str:
        """Try to extract ticker name from entry data.

        Falls back to ticker symbol itself.
        """
        # Common A-share names (extensible)
        KNOWN_NAMES: Dict[str, str] = {
            "600519": "贵州茅台",
            "000001": "平安银行",
            "000002": "万科A",
            "000858": "五粮液",
            "601318": "中国平安",
            "600036": "招商银行",
            "600276": "恒瑞医药",
            "000333": "美的集团",
            "000651": "格力电器",
            "601166": "兴业银行",
            "600030": "中信证券",
            "002415": "海康威视",
        }

        if ticker in KNOWN_NAMES:
            return KNOWN_NAMES[ticker]
        return ticker

    @staticmethod
    def _write_page(path: Path, content: str) -> None:
        """Write a wiki page to disk.

        Args:
            path: Output file path.
            content: Markdown string to write.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
