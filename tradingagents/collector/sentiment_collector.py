"""Sentiment collector — runs every 15 minutes.

Fetches global financial news, analyzes sentiment via LLM,
and writes a structured summary into KB.
"""

import asyncio
import logging
from datetime import date, datetime
from typing import Optional

from ..dataflows.akshare import get_global_news
from ..kb import KnowledgeBase

logger = logging.getLogger(__name__)


class SentimentCollector:
    """Collects global financial news and produces a sentiment analysis."""

    def __init__(self, kb: KnowledgeBase, config: dict, llm=None):
        self.kb = kb
        self.config = config
        self._llm = llm

    def set_llm(self, llm):
        self._llm = llm

    @staticmethod
    def _is_trading_day() -> bool:
        """Simple weekday check — Mon-Fri is trading day."""
        return date.today().weekday() < 5

    async def collect(self) -> Optional[dict]:
        """Fetch raw news, analyze sentiment via LLM, and store in KB."""
        if not self._is_trading_day():
            logger.debug("Non-trading day — skipping sentiment collection")
            return None

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
        """Fetch global financial news for sentiment analysis."""
        try:
            today = date.today()

            result = await asyncio.to_thread(
                get_global_news,
                today.isoformat(),
                look_back_days=1,  # Only last 24h
                limit=10,          # Top 10 articles
            )

            if not result or "No news" in result:
                return None

            # Parse markdown into structured list
            lines = result.strip().split('\n')
            articles = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('*') and not line.startswith('-'):
                    articles.append({"text": line, "source": "global"})
                elif line.startswith('**') and line.endswith('**'):
                    articles.append({"title": line.strip('*'), "source": "global"})

            # If parsing gave nothing, use raw lines
            if not articles:
                articles = [{"text": l.strip(), "source": "global"} for l in lines if l.strip()[:3] != '---']

            return articles if articles else None
        except Exception as e:
            logger.warning("Sentiment fetch failed: %s", e)
            return None

    async def _summarize(self, raw: list) -> str:
        """Use LLM or fallback for sentiment analysis."""
        if not raw:
            return "今日暂无舆情数据。"

        # Format raw into readable text for LLM
        news_text = "\n".join(
            a.get("title", a.get("text", "")) for a in raw[:10]
        )

        if self._llm:
            try:
                prompt = f"""分析以下财经新闻的情感倾向，用中文输出2-3条要点，包含整体情绪（正面/中性/负面）和关键信号。

新闻列表：
{news_text}"""
                resp = self._llm.invoke(prompt)
                content = resp.content if hasattr(resp, 'content') else str(resp)
                return content.strip() or f"今日采集{len(raw)}条财经新闻。"
            except Exception as e:
                logger.warning("LLM sentiment analysis failed: %s", e)

        # Fallback
        return f"今日采集{len(raw)}条财经新闻，整体情绪中性。"
