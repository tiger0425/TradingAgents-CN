import asyncio
import logging
from datetime import date, datetime
from typing import Optional

from ..dataflows.akshare import get_global_news
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

    @staticmethod
    def _is_trading_day() -> bool:
        return date.today().weekday() < 5

    async def collect(self) -> Optional[dict]:
        if not self._is_trading_day():
            logger.debug("Non-trading day — skipping policy monitoring")
            return None
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
        """Fetch latest policy/financial news using akshare global news."""
        try:
            today = date.today()
            result = await asyncio.to_thread(
                get_global_news,
                today.isoformat(),
                look_back_days=2,  # Last 2 days for policy coverage
                limit=20,          # More articles to find policy-related ones
            )

            if not result or "No news" in result:
                return None

            # Build structured result with title field for _is_new() dedup
            lines = result.strip().split("\n")
            # Find the first meaningful title line
            title = ""
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("*") and not line.startswith("-") and not line.startswith("|") and not line.startswith(">"):
                    title = line[:100]
                    break

            return {
                "source": "akshare_global_news",
                "title": title or f"财经动态 {today.isoformat()}",
                "content": result[:2000],  # Keep within token limits
                "collected_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.warning("Policy news fetch failed: %s", e)
            return None

    async def _analyze(self, raw: dict) -> str:
        """Use LLM to analyze policy impact."""
        content = raw.get("content", "")
        if not content:
            return "今日暂无政策动态。"

        if self._llm:
            try:
                prompt = f"""分析以下财经新闻中的政策动态，用中文输出2-3条要点。重点关注：央行/证监会政策变化、产业政策、监管动态。

新闻：
{content[:2000]}"""
                resp = self._llm.invoke(prompt)
                result = resp.content if hasattr(resp, "content") else str(resp)
                return result.strip() or "今日财经动态已更新。"
            except Exception as e:
                logger.warning("LLM policy analysis failed: %s", e)

        # Fallback
        return f"今日财经动态：{raw.get('title', '')}"

    def _is_new(self, raw: dict) -> bool:
        title = raw.get("title", "")
        if title in self._seen_policies:
            return False
        return True
