import logging
from datetime import datetime
from typing import Optional

from ..kb import KnowledgeBase

logger = logging.getLogger(__name__)


class SentimentCollector:
    def __init__(self, kb: KnowledgeBase, config: dict, llm=None):
        self.kb = kb
        self.config = config
        self._llm = llm

    def set_llm(self, llm):
        self._llm = llm

    async def collect(self) -> Optional[dict]:
        try:
            raw = await self._fetch_sentiment_raw()
            if not raw:
                return None
            summary = await self._summarize(raw)
            entry = {
                "collected_at": datetime.now().isoformat(),
                "data": summary,
            }
            self.kb.save("sentiment_report", entry)
            return entry
        except Exception as e:
            logger.warning("Sentiment collection failed: %s", e)
            return None

    async def _fetch_sentiment_raw(self) -> Optional[list]:
        return None

    async def _summarize(self, raw: list) -> str:
        return ""
