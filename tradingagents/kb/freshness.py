"""Freshness management for KB entries.

Each collection has:
- freshness_ttl: seconds before FRESH → STALE
- stale_ttl: seconds before STALE → EXPIRED
"""

from datetime import datetime, timedelta
from typing import Dict

# --- freshness constants ---
FRESH = "FRESH"
STALE = "STALE"
EXPIRED = "EXPIRED"

# Collection-specific TTLs (seconds)
COLLECTION_TTLS: Dict[str, Dict[str, int]] = {
    "market_snapshot":    {"freshness_ttl": 1800,  "stale_ttl": 7200},
    "stock_snapshot":     {"freshness_ttl": 3600,  "stale_ttl": 14400},
    "policy_brief":       {"freshness_ttl": 7200,  "stale_ttl": 86400},
    "sentiment_report":   {"freshness_ttl": 900,   "stale_ttl": 3600},
    "announcement_brief": {"freshness_ttl": 3600,  "stale_ttl": 21600},
}


class FreshnessManager:
    """Manages freshness labels for all KB collections."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.ttls = COLLECTION_TTLS

    def compute_freshness(self, collection_name: str, collected_at: str) -> str:
        """Compute freshness label for an entry based on its collection and timestamp."""
        ttls = self.ttls.get(collection_name)
        if not ttls:
            return FRESH  # unknown collection, assume fresh

        try:
            ts = datetime.fromisoformat(collected_at)
        except (ValueError, TypeError):
            return STALE

        age = (datetime.now() - ts).total_seconds()

        if age > ttls["stale_ttl"]:
            return EXPIRED
        elif age > ttls["freshness_ttl"]:
            return STALE
        return FRESH

    def maintain(self):
        """Walk all KB entries and update freshness labels."""
        # This is a placeholder — actual implementation will iterate
        # over collection directories and update freshness in-place.
        pass
