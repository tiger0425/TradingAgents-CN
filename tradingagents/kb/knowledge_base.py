"""Knowledge Base — The collective memory of the digital financial team.

Background collectors write structured research here 24/7.
Event-driven layer queries KB before launching agents.

Data is stored under ~/.tradingagents/kb/ as:
  - shared/   — market snapshots, policy briefs, sentiment (shared by all users)
  - users/    — per-user stock snapshots, announcement tracking
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .freshness import FreshnessManager, FRESH, STALE, EXPIRED

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Central knowledge base for the trading agents platform."""

    def __init__(self, base_dir: str = "~/.tradingagents/kb"):
        self.base_dir = Path(base_dir).expanduser()
        self.shared_dir = self.base_dir / "shared"
        self.users_dir = self.base_dir / "users"
        self.freshness = FreshnessManager(str(self.base_dir))

        # Ensure directories exist
        for coll_name in ["market_snapshot", "stock_snapshot", "policy_brief",
                           "sentiment_report", "announcement_brief"]:
            (self.shared_dir / coll_name).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save(self, collection: str, data: Dict[str, Any],
             user_id: str = None):
        """Save a KB entry.

        Args:
            collection: e.g. "market_snapshot", "stock_snapshot"
            data: Must include "collected_at" (ISO timestamp) and "data" (content)
            user_id: If given, saved under users/{user_id}/ instead of shared/
        """
        data.setdefault("collected_at", datetime.now().isoformat())
        data["freshness"] = self.freshness.compute_freshness(
            collection, data["collected_at"]
        )

        if user_id:
            target_dir = self.users_dir / user_id / collection
        else:
            target_dir = self.shared_dir / collection
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = self._build_filename(collection, data)
        filepath = target_dir / filename
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        logger.debug("KB saved: %s/%s", collection, filename)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_latest(self, collection: str, user_id: str = None,
                   ticker: str = None) -> Optional[Dict]:
        """Get the most recent entry from a collection."""
        if user_id:
            target_dir = self.users_dir / user_id / collection
        else:
            target_dir = self.shared_dir / collection

        if not target_dir.exists():
            return None

        files = sorted(target_dir.glob("*.json"), reverse=True)
        for f in files:
            entry = json.loads(f.read_text())
            if ticker and entry.get("ticker") != ticker:
                continue
            return entry
        return None

    def query(self, collection: str, user_id: str = None,
              **filters) -> List[Dict]:
        """Query entries matching filters.

        Args:
            collection: Collection name
            user_id: Optional user scope
            **filters: key=value pairs to filter by (e.g. ticker="600519")
        """
        if user_id:
            target_dir = self.users_dir / user_id / collection
        else:
            target_dir = self.shared_dir / collection

        if not target_dir.exists():
            return []

        results = []
        for f in target_dir.glob("*.json"):
            entry = json.loads(f.read_text())
            if all(entry.get(k) == v for k, v in filters.items()):
                results.append(entry)
        return sorted(results, key=lambda e: e.get("collected_at", ""), reverse=True)

    # ------------------------------------------------------------------
    # Event-driven query (used by LLMPlanner)
    # ------------------------------------------------------------------

    def query_for_event(self, trigger, context) -> Dict[str, Any]:
        results = {}

        market = self.get_latest("market_snapshot")
        if market and market.get("freshness") == FRESH:
            results["market_snapshot"] = market

        if getattr(context, "ticker", ""):
            stock = self.get_latest("stock_snapshot", ticker=context.ticker)
            if stock and stock.get("freshness") in (FRESH, STALE):
                results["stock_snapshot"] = stock

        industry = getattr(context, "industry", "")
        if industry:
            policies = self.query("policy_brief")
            matching = [p for p in policies if industry in str(p.get("data", ""))]
            if matching:
                results["policy_briefs"] = matching

        coverage, missing = self._calculate_coverage(results, trigger)
        return {
            "results": list(results.values()),
            "coverage_score": coverage,
            "missing_aspects": missing,
        }

    def _calculate_coverage(self, results: Dict, trigger) -> tuple:
        required = {
            "晨会": ["market_snapshot", "announcement_brief"],
            "午评": ["market_snapshot"],
            "收盘复盘": ["market_snapshot"],
            "周日选股": ["market_snapshot"],
        }
        task = getattr(trigger, "task", "") or getattr(trigger, "type", "")
        needed = required.get(task, ["market_snapshot"])
        if not needed:
            return 1.0, []
        covered = sum(1 for n in needed if n in results)
        missing = [n for n in needed if n not in results]
        return covered / len(needed), missing

    # ------------------------------------------------------------------
    # Freshness summary for dashboard
    # ------------------------------------------------------------------

    def get_freshness_summary(self) -> Dict[str, Any]:
        """Return a summary of KB freshness for the dashboard."""
        summary = {}
        for coll_name in ["market_snapshot", "policy_brief",
                           "sentiment_report", "announcement_brief"]:
            latest = self.get_latest(coll_name)
            summary[coll_name] = {
                "freshness": latest["freshness"] if latest else "MISSING",
                "age_seconds": (
                    (datetime.now() - datetime.fromisoformat(latest["collected_at"])).total_seconds()
                    if latest else None
                ),
                "count": len(list((self.shared_dir / coll_name).glob("*.json")))
            }
        return summary

    def count_all(self) -> int:
        total = 0
        for coll_name in self.shared_dir.iterdir():
            if coll_name.is_dir():
                total += len(list(coll_name.glob("*.json")))
        if self.users_dir.exists():
            for user_dir in self.users_dir.iterdir():
                if user_dir.is_dir():
                    for coll in user_dir.iterdir():
                        if coll.is_dir():
                            total += len(list(coll.glob("*.json")))
        return total

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filename(collection: str, data: Dict) -> str:
        ts = data.get("collected_at", "").replace(":", "-")
        ticker = data.get("ticker", "")
        if ticker:
            return f"{ts}_{ticker}.json"
        return f"{ts}.json"

    def maintain_freshness(self):
        """Trigger freshness label updates across all collections."""
        self.freshness.maintain()
