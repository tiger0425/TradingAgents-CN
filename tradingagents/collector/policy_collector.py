import logging
from datetime import datetime
from typing import Optional

from ..kb import KnowledgeBase

logger = logging.getLogger(__name__)


class PolicyCollector:
    def __init__(self, kb: KnowledgeBase, config: dict, llm=None):
        self.kb = kb
        self.config = config
        self._llm = llm
        self._seen_policies = set()

    def set_llm(self, llm):
        self._llm = llm

    async def collect(self) -> Optional[dict]:
        try:
            raw = await self._fetch_policy_news()
            if not raw or not self._is_new(raw):
                return None
            analysis = await self._analyze(raw)
            entry = {
                "source": raw.get("source", ""),
                "title": raw.get("title", ""),
                "collected_at": datetime.now().isoformat(),
                "data": analysis,
            }
            self.kb.save("policy_brief", entry)
            self._seen_policies.add(raw.get("title", ""))
            logger.info("Policy brief saved: %s", raw.get("title"))
            return entry
        except Exception as e:
            logger.warning("Policy monitoring failed: %s", e)
            return None

    async def _fetch_policy_news(self) -> Optional[dict]:
        return None

    async def _analyze(self, raw: dict) -> str:
        return ""

    def _is_new(self, raw: dict) -> bool:
        title = raw.get("title", "")
        if title in self._seen_policies:
            return False
        return True
