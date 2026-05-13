"""Freshness management for KB entries.

Each collection has:
- freshness_ttl: seconds before FRESH → STALE
- stale_ttl: seconds before STALE → EXPIRED
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple

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
        logger = logging.getLogger(__name__)
        base = Path(self.base_dir).expanduser()

        updated = 0
        checked = 0

        # Walk shared/ and users/ directories
        for scope_dir in [base / "shared", base / "users"]:
            if not scope_dir.exists():
                continue

            if scope_dir.name == "users":
                # users/{user_id}/{collection_name}/
                for user_dir in scope_dir.iterdir():
                    if user_dir.is_dir():
                        for coll_dir in user_dir.iterdir():
                            if coll_dir.is_dir():
                                checked, updated = self._process_collection(
                                    coll_dir, coll_dir.name, checked, updated, logger
                                )
            else:
                # shared/{collection_name}/
                for coll_dir in scope_dir.iterdir():
                    if coll_dir.is_dir():
                        checked, updated = self._process_collection(
                            coll_dir, coll_dir.name, checked, updated, logger
                        )

        logger.info("KB freshness maintained: %d checked, %d updated", checked, updated)

    def _process_collection(self, coll_dir: Path, coll_name: str, checked: int, updated: int, logger: logging.Logger) -> Tuple[int, int]:
        """Process all JSON files in a collection directory."""
        for f in sorted(coll_dir.glob("*.json")):
            checked += 1
            try:
                data = json.loads(f.read_text())
                old_freshness = data.get("freshness", "")
                new_freshness = self.compute_freshness(
                    coll_name, data.get("collected_at", "")
                )
                if old_freshness != new_freshness:
                    data["freshness"] = new_freshness
                    f.write_text(json.dumps(data, ensure_ascii=False, indent=2))
                    updated += 1
            except Exception:
                logger.warning("Failed to process KB entry: %s", f)
                continue
        return checked, updated
