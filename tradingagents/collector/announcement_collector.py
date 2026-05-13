"""Announcement scanner — runs every hour.

Scans the full market for new announcements, performs deep-dive interpretation
for watchlist and hot stocks, and writes structured summaries into KB.
"""

import asyncio
import logging
from datetime import date, datetime
from typing import List, Optional

from ..dataflows.akshare import get_individual_notices
from ..kb import KnowledgeBase
from ..portfolio.portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)


class AnnouncementCollector:
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

    async def collect(self, watchlist: List[str] = None,
                      hot_stocks: List[str] = None) -> Optional[dict]:
        """Scan announcements and write to KB."""
        if not self._is_trading_day():
            logger.debug("Non-trading day — skipping announcement scan")
            return None

        try:
            raw = await self._fetch_announcements()
            if not raw:
                return None

            # Process each ticker's announcements
            targets = watchlist or []
            targets = list(set(targets + (hot_stocks or [])))
            for ticker, notice_text in raw.items():
                summary = await self._annotate(ticker, notice_text)
                entry = {
                    "ticker": ticker,
                    "collected_at": datetime.now().isoformat(),
                    "data": summary,
                }
                self.kb.save("announcement_brief", entry)

            logger.info("Announcement scan complete — %d tickers processed", len(raw))
            return {"processed": len(raw)}
        except Exception as e:
            logger.warning("Announcement scan failed: %s", e)
            return None

    async def _fetch_announcements(self) -> Optional[dict]:
        """Fetch announcements for all watched stocks."""
        try:
            pm = PortfolioManager()
            tickers = set()
            for user_id in ["default"]:
                for h in pm.get_holdings_list(user_id):
                    ticker = h.get("ticker", "")
                    if ticker:
                        tickers.add(ticker)
                for w in pm.get_watchlist(user_id):
                    ticker = w.get("ticker", "")
                    if ticker:
                        tickers.add(ticker)

            if not tickers:
                logger.debug("No stocks in portfolio/watchlist — skipping announcements")
                return None

            results = {}
            for ticker in sorted(tickers):
                raw = await asyncio.to_thread(
                    get_individual_notices,
                    ticker,
                    days_back=1,
                )
                if raw and "No data" not in raw and "Error" not in raw:
                    results[ticker] = raw

            return results if results else None
        except Exception as e:
            logger.warning("Announcement fetch failed: %s", e)
            return None

    async def _annotate(self, ticker: str, raw_announcements: str) -> str:
        """Summarize announcements for a ticker using LLM or fallback."""
        if not raw_announcements:
            return f"{ticker}: 暂无新公告。"

        if self._llm:
            try:
                prompt = f"""用中文简要总结以下{ticker}的最新公告要点（1-2句话）。

公告：
{raw_announcements[:1500]}"""
                resp = self._llm.invoke(prompt)
                content = resp.content if hasattr(resp, 'content') else str(resp)
                return content.strip() or f"{ticker}: 有新的公告，请查看详情。"
            except Exception as e:
                logger.warning("LLM annotate failed for %s: %s", ticker, e)

        # Fallback: extract first meaningful line
        lines = raw_announcements.strip().split('\n')
        title_line = next((l.strip() for l in lines if l.strip() and not l.startswith('#') and not l.startswith('-') and not l.startswith('*') and not l.startswith('|')), "")
        return f"{ticker}: {title_line[:100]}" if title_line else f"{ticker}: 有新的公告。"
