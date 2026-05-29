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
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .freshness import FreshnessManager, FRESH, STALE, EXPIRED

# 时效衰减配置（半衰期，秒）
# decay = 0.5 ^ (age / half_life)
DECAY_CONFIG: Dict[str, int] = {
    "market_snapshot":     600,    # 市场快照：10 分钟半衰期
    "sentiment_report":    300,    # 舆情报告：5 分钟半衰期
    "announcement_brief":  1800,   # 公告摘要：30 分钟半衰期
    "policy_brief":        3600,   # 政策简报：60 分钟半衰期
    "stock_snapshot":      1800,   # 个股快照：30 分钟半衰期
}
# 衰减 < 0.25 → 标记为 stale
STALE_THRESHOLD = 0.25

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

        weighted_coverage, detail = self._calculate_coverage(results)
        return {
            "results": list(results.values()),
            "coverage_score": weighted_coverage,
            "coverage_detail": detail,
            "missing_aspects": detail.get("stale_items", []),
        }

    def _calculate_coverage(self, results: Dict) -> Tuple[float, dict]:
        """计算 KB 覆盖率（含时效衰减）。

        对 results 中每条数据计算指数衰减:
            decay = 0.5 ^ (age / half_life)
        其中 half_life 按 collection 差异化配置。

        Args:
            results: {collection_name: data_or_list} 的字典

        Returns:
            (weighted_coverage, detail_dict)
            detail_dict 包含:
                raw_coverage: float      原始覆盖率
                weighted_coverage: float 时效加权覆盖率
                stale_items: list[str]   已过时效的数据项
        """
        total_weight = 0.0
        available_weight = 0.0
        stale_items: List[str] = []

        for result_key, data in results.items():
            collection_name = self._normalize_collection_key(result_key)
            half_life = DECAY_CONFIG.get(collection_name, 1800)
            base_weight = 1.0

            if data is not None:
                # 处理 dict（单个条目）或 list（如 policy_briefs）
                if isinstance(data, list):
                    timestamps = [self._extract_timestamp(item) for item in data if isinstance(item, dict)]
                    timestamp = max(timestamps) if timestamps else 0.0
                else:
                    timestamp = self._extract_timestamp(data)

                if timestamp > 0:
                    age_seconds = time.time() - timestamp
                    decay_factor = 0.5 ** (age_seconds / half_life)
                    available_weight += base_weight * decay_factor

                    if decay_factor < STALE_THRESHOLD:
                        stale_items.append(result_key)
                else:
                    stale_items.append(result_key)

            total_weight += base_weight

        raw_coverage = available_weight / total_weight if total_weight > 0 else 0.0
        stale_penalty = len(stale_items) * 0.1
        weighted_coverage = max(0.0, raw_coverage - stale_penalty)

        return weighted_coverage, {
            "raw_coverage": raw_coverage,
            "weighted_coverage": weighted_coverage,
            "stale_items": stale_items,
        }

    @staticmethod
    def _normalize_collection_key(key: str) -> str:
        """将 results 中的 key 标准化为 collection 名称。

        处理 query_for_event 中使用的复数形式:
            policy_briefs → policy_brief
        """
        plural_to_singular = {
            "policy_briefs": "policy_brief",
            "announcement_briefs": "announcement_brief",
            "sentiment_reports": "sentiment_report",
            "market_snapshots": "market_snapshot",
            "stock_snapshots": "stock_snapshot",
        }
        return plural_to_singular.get(key, key)

    @staticmethod
    def _extract_timestamp(data) -> float:
        """从 KB 数据中提取 unix 时间戳。

        优先级: _ts > collected_at (ISO) > 0 (unknown)
        """
        ts = data.get("_ts", 0)
        if not ts:
            collected_at = data.get("collected_at", "")
            if collected_at:
                try:
                    ts = datetime.fromisoformat(collected_at).timestamp()
                except (ValueError, TypeError, OSError):
                    return 0.0
        if isinstance(ts, (int, float)) and ts > 0:
            return float(ts)
        return 0.0

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
