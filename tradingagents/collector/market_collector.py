"""Market data collector — runs every 30 minutes during trading hours.

Fetches index quotes, sector performance, fund flows, northbound money,
and writes a structured summary into KB.
"""

import asyncio
import logging
from datetime import date, datetime
from typing import Optional

from ..dataflows.market_context import fetch_market_context
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

    @staticmethod
    def _is_trading_day() -> bool:
        """Simple weekday check — Mon-Fri is trading day."""
        return date.today().weekday() < 5

    async def collect(self) -> Optional[dict]:
        """Fetch raw market data, summarize via LLM, and store in KB."""
        if not self._is_trading_day():
            logger.debug("Non-trading day — skipping market data collection")
            return None

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
        """Fetch raw market data using fetch_market_context()."""
        try:
            today = date.today().isoformat()

            # fetch_market_context is synchronous — wrap in to_thread
            result = await asyncio.to_thread(
                fetch_market_context, today, self.market_type
            )

            return {
                "market_context": result,
                "collected_at": datetime.now().isoformat(),
                "market_type": self.market_type,
            }
        except Exception as e:
            logger.warning("Market data fetch failed: %s", e)
            return None

    async def _summarize(self, raw: dict) -> str:
        """Use LLM or fallback to produce a market summary."""
        raw_text = raw.get("market_context", "")
        if not raw_text:
            return "今日暂无市场数据。"

        if self._llm:
            try:
                prompt = f"""根据以下市场数据，用中文生成3-5条要点的市场简报。每条不超过20字。

市场数据：
{raw_text}"""
                resp = self._llm.invoke(prompt)
                content = resp.content if hasattr(resp, 'content') else str(resp)
                return content.strip() or "今日市场数据采集完成。"
            except Exception as e:
                logger.warning("LLM market summary failed: %s", e)

        # Fallback: extract key points via simple rules
        return self._fallback_summary(raw_text)

    @staticmethod
    def _fallback_summary(raw_text: str) -> str:
        """Rule-based fallback when LLM is unavailable."""
        lines = raw_text.strip().split('\n')
        # Take first 5 meaningful lines, skip placeholder text
        meaningful = [
            l.strip() for l in lines
            if l.strip() and '（数据暂不可用）' not in l
        ]
        return '\n'.join(meaningful[:5]) if meaningful else "今日市场数据采集完成。"
