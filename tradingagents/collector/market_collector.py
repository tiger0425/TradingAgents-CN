"""Market data collector — runs every 30 minutes during trading hours.

Fetches index quotes, sector performance, fund flows, northbound money,
and writes a structured summary into KB.
"""

import logging
from datetime import datetime
from typing import Optional

from ..kb import KnowledgeBase

logger = logging.getLogger(__name__)


class MarketDataCollector:
    """Collects real-time market data and summarizes it via a lightweight LLM."""

    def __init__(self, kb: KnowledgeBase, config: dict, llm=None):
        self.kb = kb
        self.config = config
        self.market_type = config.get("market_type", "A_SHARE")
        self._llm = llm

    def set_llm(self, llm):
        self._llm = llm

    async def collect(self) -> Optional[dict]:
        """Fetch raw market data, summarize via LLM, and store in KB."""
        try:
            raw = await self._fetch_raw()
            if not raw:
                return None

            summary = await self._summarize(raw)
            entry = {
                "collected_at": datetime.now().isoformat(),
                "data": summary,
                "market_type": self.market_type,
            }
            self.kb.save("market_snapshot", entry)
            logger.info("Market snapshot saved to KB")
            return entry
        except Exception as e:
            logger.warning("Market data collection failed: %s", e)
            return None

    async def _fetch_raw(self) -> Optional[dict]:
        """Fetch raw market data — delegated to subclass or dataflow module."""
        # Placeholder — Phase 2 will integrate AkShare / other data sources
        return None

    async def _summarize(self, raw: dict) -> str:
        """Use lightweight LLM to produce a 3-5 bullet summary."""
        # Placeholder
        return ""
