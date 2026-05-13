"""开盘前 OHLCV 数据预取。

在交易时段开始前（09:00），预取所有持仓和自选股的 60 日 OHLCV 数据到 KB，
使 Agent 执行分析时无需等待网络请求。"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from ..kb import KnowledgeBase
from ..portfolio.portfolio_manager import PortfolioManager

logger = logging.getLogger(__name__)


class PrefetchManager:
    """Prefetch OHLCV data for portfolio/watchlist stocks before market open."""

    def __init__(self, portfolio_mgr: PortfolioManager, kb: KnowledgeBase, config: Optional[dict] = None):
        self.portfolio_mgr = portfolio_mgr
        self.kb = kb
        self.config = config or {}

    async def prefetch_all(self):
        """Prefetch 60-day OHLCV for all portfolio/watchlist stocks."""
        from ..dataflows.akshare import get_stock_data

        tickers = self._gather_all_tickers()
        if not tickers:
            logger.info("No stocks to prefetch — portfolio/watchlist empty")
            return

        today = date.today()
        start_date = (today - timedelta(days=60)).isoformat()
        end_date = today.isoformat()

        logger.info("Prefetching OHLCV for %d tickers...", len(tickers))
        success = 0

        for ticker in sorted(tickers):
            try:
                ohlcv = await asyncio.to_thread(
                    get_stock_data, ticker, start_date, end_date
                )
                if ohlcv and "No data" not in ohlcv:
                    self.kb.save("stock_snapshot", {
                        "ticker": ticker,
                        "collected_at": datetime.now().isoformat(),
                        "data": ohlcv,
                        "ohlcv_cached": True,
                    })
                    success += 1
                else:
                    logger.debug("No OHLCV data for %s", ticker)
            except Exception as e:
                logger.warning("Failed to prefetch %s: %s", ticker, e)

        logger.info("Prefetch complete: %d/%d tickers cached", success, len(tickers))

    def _gather_all_tickers(self) -> List[str]:
        """Collect all stock tickers from portfolio holdings and watchlist."""
        tickers = set()
        for h in self.portfolio_mgr.get_holdings_list("default"):
            t = h.get("ticker", "")
            if t:
                tickers.add(t)
        for w in self.portfolio_mgr.get_watchlist("default"):
            t = w.get("ticker", "")
            if t:
                tickers.add(t)
        return list(tickers)
