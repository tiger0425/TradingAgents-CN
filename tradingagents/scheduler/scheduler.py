import logging
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..collector import MarketDataCollector, AnnouncementCollector, PolicyCollector, SentimentCollector
from ..planner.schemas import Trigger, Context

logger = logging.getLogger(__name__)


class TradingAgentsScheduler:
    def __init__(self, kb, planner, portfolio_mgr, executor=None,
                 openclaw=None, config=None, data_exporter=None):
        self.kb = kb
        self.planner = planner
        self.portfolio_mgr = portfolio_mgr
        self.executor = executor
        self.openclaw = openclaw
        self.data_exporter = data_exporter
        self.config = config or {}
        self.collector_scheduler = AsyncIOScheduler()
        self.event_scheduler = AsyncIOScheduler()

    def start(self):
        self._start_collectors()
        self._start_events()
        logger.info("Dual-layer scheduler started (collectors + events)")

    def _start_collectors(self):
        llm = self.config.get("quick_think_llm")
        market = MarketDataCollector(self.kb, self.config, llm)
        announcement = AnnouncementCollector(self.kb, self.config, llm)
        policy = PolicyCollector(self.kb, self.config, llm)
        sentiment = SentimentCollector(self.kb, self.config, llm)

        self.collector_scheduler.add_job(
            market.collect, 'interval', minutes=30, id='collect_market'
        )
        self.collector_scheduler.add_job(
            announcement.collect, 'interval', hours=1, id='scan_announcements'
        )
        self.collector_scheduler.add_job(
            policy.collect, 'interval', hours=2, id='monitor_policy'
        )
        self.collector_scheduler.add_job(
            sentiment.collect, 'interval', minutes=15, id='collect_sentiment'
        )
        self.collector_scheduler.start()

    def _start_events(self):
        self.event_scheduler.add_job(
            self._morning_briefing, 'cron', day_of_week='mon-fri', hour=8, minute=50,
            id='morning_briefing',
        )
        self.event_scheduler.add_job(
            self._midday_review, 'cron', day_of_week='mon-fri', hour=12, minute=0,
            id='midday_review',
        )
        self.event_scheduler.add_job(
            self._closing_review, 'cron', day_of_week='mon-fri', hour=15, minute=10,
            id='closing_review',
        )
        self.event_scheduler.add_job(
            self._sunday_screening, 'cron', day_of_week='sun', hour=9, minute=0,
            id='sunday_screening',
        )
        self.event_scheduler.add_job(
            self.kb.maintain_freshness, 'interval', hours=1, id='kb_maintenance',
        )
        self.event_scheduler.add_job(
            self._prefetch_ohlcv, 'cron', day_of_week='mon-fri', hour=9, minute=0,
            id='prefetch_ohlcv',
        )
        self.event_scheduler.start()

    async def _morning_briefing(self):
        if not self._is_trading_day():
            return
        await self._run_event_for_all(
            task="晨会",
            timeout=10,
            report_type="morning_briefing",
        )

    async def _midday_review(self):
        if not self._is_trading_day():
            return
        await self._run_event_for_all(
            task="午评",
            timeout=5,
            report_type="midday_review",
        )

    async def _closing_review(self):
        if not self._is_trading_day():
            return
        await self._run_event_for_all(
            task="收盘复盘",
            timeout=10,
            report_type="closing_review",
        )

    async def _sunday_screening(self):
        await self._run_event_for_all(
            task="周日选股",
            timeout=20,
            report_type="weekly_screening",
        )

    async def _prefetch_ohlcv(self):
        if not self._is_trading_day():
            return
        try:
            from ..collector.prefetch import PrefetchManager
            pf = PrefetchManager(self.portfolio_mgr, self.kb)
            await pf.prefetch_all()
        except Exception:
            logger.exception("OHLCV prefetch failed")

    async def _run_event_for_all(self, task, timeout, report_type):
        for user_id in self._active_users():
            await self._run_event_for_user(user_id, task, timeout, report_type)

    async def _run_event_for_user(self, user_id, task, timeout, report_type):
        try:
            portfolio = self.portfolio_mgr.load(user_id)
            portfolio_summary = self._summarize_portfolio(portfolio)

            trigger = Trigger(
                type="scheduled",
                task=task,
                timeout_minutes=timeout,
            )
            industry = ""
            ctx_ticker = portfolio.get("ticker", "")
            if ctx_ticker:
                try:
                    from ..dataflows.a_stock_data import get_industry
                    industry = get_industry(ctx_ticker)
                except Exception:
                    industry = ""

            context = Context(
                user_id=user_id,
                ticker=ctx_ticker,
                industry=industry,
                portfolio_summary=portfolio_summary,
            )

            plan = self.planner.plan(trigger, context)
            logger.info(
                "%s planned for user %s (intent=%s mode=%s steps=%d)",
                task, user_id,
                plan.get("intent", "?"),
                plan.get("_generation_mode", "?"),
                len(plan.get("workflow", [])),
            )

            if self.executor:
                result = self.executor.execute(plan, trigger, context)
                report = result.get("final_report", "")
                logger.info(
                    "%s executed for user %s (report=%d chars)",
                    task, user_id, len(report),
                )

                if self.openclaw and report:
                    await self._push_report(user_id, report, report_type)

                if self.data_exporter:
                    self.data_exporter.export_all(user_id)
            else:
                logger.warning(
                    "%s skipped for user %s: no executor configured", task, user_id
                )

        except Exception:
            logger.exception("%s failed for user %s", task, user_id)

    async def _push_report(self, user_id, report, report_type):
        try:
            await self.openclaw.push(
                user_id=user_id,
                report=report,
                report_type=report_type,
            )
        except Exception:
            logger.exception("Push failed for user %s (%s)", user_id, report_type)

    @staticmethod
    def _summarize_portfolio(portfolio):
        holdings = portfolio.get("holdings", [])
        if not holdings:
            return ""
        return ", ".join(
            f"{h.get('ticker', '?')}@{h.get('cost_price', 0)}x{h.get('quantity', 0)}"
            for h in holdings
        )

    def _active_users(self):
        try:
            from ..users import UserManager
            return UserManager().get_active_users()
        except Exception:
            return ["default"]

    @staticmethod
    def _is_trading_day():
        today = date.today()
        if today.weekday() >= 5:
            return False
        return True
