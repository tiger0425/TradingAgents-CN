"""ContextAssembly node: gathers all available historical knowledge at run start.

Queries:
- AnalysisArchive → archived analyses (with confidence tags)
- TradingMemoryLog → past trading decisions with outcomes
- DataCache → cache_status snapshot

Produces ``knowledge_context`` dict injected into AgentState before graph execution.
All LLM agents read what they need from this shared context.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.cache import DataCache

logger = logging.getLogger(__name__)

# Confidence tag hierarchy (descending priority)
# CONFIRMED > SINGLE > DERIVED > CONFLICTING > STALE
CONFIDENCE_LEVELS = {
    "CONFIRMED": 4,
    "SINGLE": 3,
    "DERIVED": 2,
    "CONFLICTING": 1,
    "STALE": 0,
}

TAG_HIERARCHY = list(CONFIDENCE_LEVELS.keys())  # ["CONFIRMED", "SINGLE", "DERIVED", "CONFLICTING", "STALE"]


class ContextAssembler:
    """Gathers all available historical knowledge at run start.

    Queries:
    - AnalysisArchive → archived analyses (with confidence tags)
    - TradingMemoryLog → past trading decisions with outcomes
    - DataCache → cache_status snapshot

    Produces ``knowledge_context`` dict with:
        {
            "archived_analyses": [...],
            "past_decisions": "...",
            "ticker_signals": {...},
            "lessons": [...],
            "cache_status": {...},
            "_confidence_tags": {...},
        }
    """

    def __init__(self, config: Union[dict, str, Path, None] = None):
        """Initialize with config dict or None for defaults.

        Args:
            config: Configuration dictionary containing at minimum:
                - ``analysis_archive_dir`` — path to archive directory
                - ``knowledge_token_budget`` — max token count (default 25000)
                - ``confidence_tags_enabled`` — activate confidence system
                - ``confidence_threshold_inject`` — minimum confidence to inject
        """
        cfg = config if isinstance(config, dict) else {}
        self.config = cfg

        self.archive = AnalysisArchive(config)
        self.memory_log = TradingMemoryLog(config)

        cache_dir = cfg.get(
            "data_cache_dir",
            str(Path.home() / ".tradingagents" / "cache"),
        )
        self.data_cache = DataCache(cache_dir)

        # Config values
        self.token_budget = cfg.get("knowledge_token_budget", 25000)
        self.tags_enabled = cfg.get("confidence_tags_enabled", True)
        self.threshold_inject = cfg.get("confidence_threshold_inject", "CONFLICTING")

    # ==================================================================
    # Public API
    # ==================================================================

    def assemble(
        self,
        ticker: str,
        date: str,
        market_type: str = "A_SHARE",
    ) -> dict:
        """Gather all available historical knowledge into a structured context dict.

        Implementation:
        1. Query AnalysisArchive for archived analyses of this ticker (limit=5)
        2. Query TradingMemoryLog for past decisions string
        3. Compute ticker signal summary for last 30 days
        4. Compute confidence tags for each piece of knowledge
        5. Apply token budget (truncate if > knowledge_token_budget)
        6. Return structured dict

        Args:
            ticker: Stock ticker symbol (e.g., ``"600519"``).
            date: Analysis date in ISO format (e.g., ``"2026-05-09"``).
            market_type: ``"A_SHARE"`` or ``"US_STOCK"``.

        Returns:
            Structured ``knowledge_context`` dict with all sections populated,
            even when archives are empty (empty lists/strings as defaults).
        """
        # 1. Query AnalysisArchive
        archived_entries = self.archive.list(ticker=ticker, limit=5)

        # 2. Query TradingMemoryLog
        past_decisions = self.memory_log.get_past_context(
            ticker, n_same=5, n_cross=3
        )

        # 3. Compute signal summary (last 30 days)
        ticker_signals = self._summarize_signals(ticker)

        # 4. Extract cross-ticker lessons
        lessons = self._extract_lessons()

        # 5. Compute confidence tags
        confidence_tags = {}
        if self.tags_enabled:
            confidence_tags = self._compute_confidence(ticker, archived_entries)

        # 6. Cache status snapshot
        cache_status = self._cache_status_snapshot()

        # Build the context dict
        context = {
            "archived_analyses": self._format_archived_entries(archived_entries),
            "past_decisions": past_decisions,
            "ticker_signals": ticker_signals,
            "lessons": lessons,
            "cache_status": cache_status,
            "_confidence_tags": confidence_tags,
            "_confidence_metadata": {
                "ticker": ticker,
                "date": date,
                "market_type": market_type,
                "confidence_tags_enabled": self.tags_enabled,
                "threshold_inject": self.threshold_inject,
                "budget_applied": self.token_budget,
            },
        }

        # 5. Apply token budget
        context = self._apply_budget(context)

        return context

    # ==================================================================
    # Signal summary
    # ==================================================================

    def _summarize_signals(self, ticker: str, days: int = 30) -> dict:
        """Compute a signal distribution summary for *ticker* over *days*.

        Uses AnalysisArchive.summary() for quick signal distribution without
        loading full entry content. Falls back to empty dict when archive
        has no entries for this ticker.

        Returns dict with:
            {
                "ticker": str,
                "period_days": int,
                "total_entries": int,
                "by_decision": {decision: count},
                "by_type": {entry_type: count},
                "trend": [{date, decision, rating}, ...],
            }
        """
        try:
            summary = self.archive.summary(ticker, days=days)
            return summary
        except Exception as e:
            logger.debug("Signal summary unavailable for %s: %s", ticker, e)
            return {
                "ticker": ticker,
                "period_days": days,
                "total_entries": 0,
                "by_decision": {},
                "by_type": {},
                "trend": [],
            }

    # ==================================================================
    # Lessons extraction
    # ==================================================================

    def _extract_lessons(self) -> List[dict]:
        """Extract cross-ticker lessons from memory log entries.

        Returns list of dicts with:
            {ticker, date, rating, reflection_summary}
        """
        entries = self.memory_log.load_entries()
        lessons = []
        for e in entries:
            if e.get("pending"):
                continue
            if e.get("reflection"):
                # Truncate reflection to first 200 chars as lesson summary
                reflection = e["reflection"]
                if len(reflection) > 200:
                    reflection = reflection[:200] + "..."
                lessons.append({
                    "ticker": e.get("ticker", ""),
                    "date": e.get("date", ""),
                    "rating": e.get("rating", ""),
                    "reflection_summary": reflection,
                })
        # Most recent first
        lessons.sort(key=lambda x: x["date"], reverse=True)
        return lessons[:10]  # Cap at 10 lessons

    # ==================================================================
    # Confidence computation (rule-based)
    # ==================================================================

    def _compute_confidence(
        self, ticker: str, entries: list
    ) -> dict:
        """Compute confidence tags for a ticker based on historical entries.

        Tags:
        - CONFIRMED: 3+ same-direction signals in last 30 days
        - SINGLE: only 1 analysis found
        - CONFLICTING: mixed buy/sell signals
        - STALE: last analysis > 90 days ago
        - DERIVED: cross-ticker pattern (reserved for future)

        Returns dict with:
            {
                "overall": "CONFIRMED"|"SINGLE"|"CONFLICTING"|"STALE",
                "entries": {entry_id: "CONFIRMED"|...},
                "signal_distribution": {buy: N, sell: N, hold: N},
                "label": "中文标签",
            }
        """
        if not entries:
            return {
                "overall": "SINGLE",
                "entries": {},
                "signal_distribution": {"buy": 0, "sell": 0, "hold": 0},
                "label": "无历史分析记录",
                "level": CONFIDENCE_LEVELS["SINGLE"],
            }

        now = datetime.now()
        cutoff_30d = now - timedelta(days=30)
        cutoff_90d = now - timedelta(days=90)

        # Classify each entry
        signal_dist = {"buy": 0, "sell": 0, "hold": 0}
        entry_tags: Dict[str, str] = {}
        recent_same_direction = 0

        for e in entries:
            eid = e.get("id", "")
            decision = e.get("decision", "").lower()
            date_str = e.get("date", "")

            if "buy" in decision or "overweight" in decision:
                signal_dist["buy"] += 1
                direction = "bullish"
            elif "sell" in decision or "underweight" in decision:
                signal_dist["sell"] += 1
                direction = "bearish"
            else:
                signal_dist["hold"] += 1
                direction = "neutral"

            # Check recency
            try:
                entry_date = datetime.strptime(date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                entry_date = now

            # Per-entry confidence tag
            if entry_date < cutoff_90d:
                entry_tags[eid] = "STALE"
            elif entry_date >= cutoff_30d:
                # Recent entry - will be evaluated with others
                entry_tags[eid] = "RECENT"  # placeholder, resolved below
            else:
                entry_tags[eid] = "STALE"  # >30d but <90d

        # Count recent same-direction entries
        # Entries from the last 30 days
        recent_30d = [
            e for e in entries
            if _date_in_range(e.get("date", ""), cutoff_30d, now)
        ]

        # Determine same-direction count for recent entries
        buy_signals = [e for e in recent_30d if _is_bullish(e)]
        sell_signals = [e for e in recent_30d if _is_bearish(e)]

        # Overall confidence
        if len(entries) == 1:
            # Single entry: check staleness first
            entry_date = _parse_date(entries[0].get("date", ""))
            if entry_date < cutoff_90d:
                overall = "STALE"
            else:
                overall = "SINGLE"
        elif bool(buy_signals) and bool(sell_signals):
            # Mixed signals: both buy and sell in recent 30 days
            overall = "CONFLICTING"
        elif len(buy_signals) >= 3 or len(sell_signals) >= 3:
            overall = "CONFIRMED"
        else:
            # Check for staleness
            newest_date = max(
                (_parse_date(e.get("date", "")) for e in entries),
                default=datetime.min,
            )
            if newest_date < cutoff_90d:
                overall = "STALE"
            else:
                # Has recent entries but < 3 same direction
                overall = "SINGLE" if len(recent_30d) <= 1 else "CONFIRMED"

        # Map overall to label
        labels = {
            "CONFIRMED": "多次确认信号",
            "SINGLE": "单一分析记录",
            "CONFLICTING": "信号冲突",
            "STALE": "分析记录陈旧",
            "DERIVED": "跨标推导",
        }

        return {
            "overall": overall,
            "entries": entry_tags,
            "signal_distribution": signal_dist,
            "label": labels.get(overall, overall),
            "level": CONFIDENCE_LEVELS.get(overall, 0),
        }

    def filter_by_confidence(
        self, context: dict, tags: dict
    ) -> dict:
        """Filter ``archived_analyses`` entries below the configured confidence threshold.

        Returns a new context dict with only entries meeting the threshold.
        """
        threshold_level = CONFIDENCE_LEVELS.get(self.threshold_inject, 1)
        overall_level = tags.get("level", 0)

        if overall_level < threshold_level:
            # Overall confidence below threshold — clear archived analyses
            filtered = dict(context)
            filtered["archived_analyses"] = []
            filtered["_confidence_tags"] = tags
            filtered["_filtered_out_reason"] = (
                f"Confidence level {tags.get('overall', 'UNKNOWN')} "
                f"below threshold {self.threshold_inject}"
            )
            return filtered

        return context

    # ==================================================================
    # Token budget control
    # ==================================================================

    def _apply_budget(self, context: dict) -> dict:
        """Apply token budget to the knowledge context.

        Priority order (kept longest):
        1. archived_analyses (most important for decision quality)
        2. past_decisions
        3. ticker_signals
        4. lessons
        5. cache_status (most expendable)

        Uses approximate token counting: 1 token ≈ 4 chars for CJK text.
        """
        budget = self.token_budget
        current_tokens = self._count_tokens(context)

        if current_tokens <= budget:
            context["_budget_applied"] = {
                "budget": budget,
                "before_tokens": current_tokens,
                "after_tokens": current_tokens,
                "truncated": False,
            }
            return context

        # Build a copy to mutate
        result = dict(context)

        # Priority removal order (lowest priority first):
        # cache_status → lessons → ticker_signals → past_decisions → archived_analyses
        removal_order = [
            "cache_status",
            "lessons",
            "ticker_signals",
            "past_decisions",
            "archived_analyses",
        ]

        for key in removal_order:
            if key not in result:
                continue
            # Try truncating the field
            if isinstance(result[key], str):
                # Truncate string to fit budget
                max_chars = budget * 4  # ≈ tokens-to-chars
                if len(result[key]) > max_chars:
                    result[key] = result[key][:max_chars] + "\n\n[truncated for budget]"
            elif isinstance(result[key], list):
                # Truncate list items
                while (self._count_tokens(result) > budget
                       and len(result[key]) > 0):
                    result[key] = result[key][:len(result[key]) - 1]
                if len(result[key]) == 0 and self._count_tokens(result) > budget:
                    # Tough: remove the key entirely
                    result[key] = [] if key == "lessons" else {}
            elif isinstance(result[key], dict):
                # Clear dict
                if self._count_tokens(result) > budget:
                    result[key] = {}

        result["_budget_applied"] = {
            "budget": budget,
            "before_tokens": current_tokens,
            "after_tokens": self._count_tokens(result),
            "truncated": self._count_tokens(result) < current_tokens,
        }

        return result

    @staticmethod
    def _count_tokens(data) -> int:
        """Approximate token count: 1 token ≈ 4 characters for CJK text."""
        import json
        text = json.dumps(data, ensure_ascii=False, default=str)
        return max(1, len(text) // 4)

    # ==================================================================
    # Cache status
    # ==================================================================

    def _cache_status_snapshot(self) -> dict:
        """Return a lightweight snapshot of cache state.

        Checks existence of known cache directories without loading data.
        """
        cache_dir = Path(self.data_cache._cache_dir)
        status = {
            "cache_dir": str(cache_dir),
            "exists": cache_dir.exists(),
        }
        if cache_dir.exists():
            try:
                namespaces = {
                    "ohlcv": (cache_dir / "ohlcv").exists(),
                    "benchmark": (cache_dir / "benchmark").exists(),
                    "fundamentals": (cache_dir / "fundamentals").exists(),
                }
                status["namespaces"] = namespaces
                # File counts
                status["file_counts"] = {
                    ns: len(list((cache_dir / ns).glob("*")))
                    for ns, exists in namespaces.items()
                    if exists
                }
            except OSError:
                status["namespaces"] = {}
                status["file_counts"] = {}
        return status

    # ==================================================================
    # Helpers
    # ==================================================================

    @staticmethod
    def _format_archived_entries(entries: list) -> List[dict]:
        """Format raw archive entry metadata into a consistent shape for agents.

        Each entry becomes:
            {
                "id": entry_id,
                "date": "2026-05-09",
                "type": "morning-scan",
                "ticker": "600519",
                "decision": "Buy",
                "rating": "Buy",
                "analysts": [...],
            }
        """
        formatted = []
        for e in entries:
            formatted.append({
                "id": e.get("id", ""),
                "date": e.get("date", ""),
                "type": e.get("type", ""),
                "ticker": e.get("ticker", ""),
                "decision": e.get("decision", ""),
                "rating": e.get("rating", ""),
                "analysts": e.get("analysts", []),
            })
        return formatted


# ======================================================================
# Module-level helpers
# ======================================================================


def _is_bullish(entry: dict) -> bool:
    """Check if an entry has a bullish (Buy/Overweight) decision."""
    decision = (entry.get("decision") or "").lower()
    return "buy" in decision or "overweight" in decision


def _is_bearish(entry: dict) -> bool:
    """Check if an entry has a bearish (Sell/Underweight) decision."""
    decision = (entry.get("decision") or "").lower()
    return "sell" in decision or "underweight" in decision


def _parse_date(date_str: str) -> datetime:
    """Parse date string to datetime, returning datetime.min on failure."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return datetime.min


def _date_in_range(date_str: str, start: datetime, end: datetime) -> bool:
    """Check if date_str falls within [start, end]."""
    dt = _parse_date(date_str)
    return start <= dt <= end
