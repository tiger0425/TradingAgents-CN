"""Announcement scanner — runs every hour.

Scans the full market for new announcements, performs deep-dive interpretation
for watchlist and hot stocks, and writes structured summaries into KB.
"""

import logging
from datetime import datetime
from typing import List, Optional

from ..kb import KnowledgeBase

logger = logging.getLogger(__name__)


class AnnouncementCollector:
    def __init__(self, kb: KnowledgeBase, config: dict, llm=None):
        self.kb = kb
        self.config = config
        self._llm = llm

    def set_llm(self, llm):
        self._llm = llm

    async def collect(self, watchlist: List[str] = None,
                      hot_stocks: List[str] = None) -> Optional[dict]:
        """Scan announcements and write to KB."""
        try:
            raw = await self._fetch_announcements()
            if not raw:
                return None

            # Summarize announcements for watchlist / hot stocks
            targets = (watchlist or []) + (hot_stocks or [])
            for ticker in set(targets):
                if ticker in raw:
                    summary = await self._annotate(ticker, raw[ticker])
                    entry = {
                        "ticker": ticker,
                        "collected_at": datetime.now().isoformat(),
                        "data": summary,
                    }
                    self.kb.save("announcement_brief", entry)

            logger.info("Announcement scan complete — %d tickers processed", len(targets))
            return {"processed": len(targets)}
        except Exception as e:
            logger.warning("Announcement scan failed: %s", e)
            return None

    async def _fetch_announcements(self) -> Optional[dict]:
        # Placeholder
        return None

    async def _annotate(self, ticker: str, raw_announcements: list) -> str:
        # Placeholder
        return ""
