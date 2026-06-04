# TradingAgents/graph/trading_graph.py

import logging
import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

from langgraph.prebuilt import ToolNode

from tradingagents.llm_clients import create_llm_client

from tradingagents.agents import *
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.agents.utils.position_state import PositionStateManager
from tradingagents.agents.utils.rating import parse_rating
from tradingagents.dataflows.utils import safe_ticker_component
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_current_price,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_market_context,
)
from tradingagents.agents.utils.a_stock_data_tools import get_cls_flash, get_hot_stock_reasons
from tradingagents.agents.utils.social_sentiment_tools import get_social_sentiment_tool

from .checkpointer import checkpoint_step, clear_checkpoint, get_checkpointer, thread_id
from .conditional_logic import ConditionalLogic
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
    ):
        """Initialize the trading agents graph and components.

        Args:
            selected_analysts: List of analyst types to include
            debug: Whether to run in debug mode
            config: Configuration dictionary. If None, uses default config
            callbacks: Optional list of callback handlers (e.g., for tracking LLM/tool stats)
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Create necessary directories
        os.makedirs(self.config["data_cache_dir"], exist_ok=True)
        os.makedirs(self.config["results_dir"], exist_ok=True)

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        # Quick LLM may use a different provider than the deep LLM.
        # The env TRADINGAGENTS_QUICK_LLM_PROVIDER is canonical; fall back
        # to the main llm_provider when unset.
        quick_provider = (
            os.getenv("TRADINGAGENTS_QUICK_LLM_PROVIDER")
            or self.config.get("quick_llm_provider")
            or self.config["llm_provider"]
        )
        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=quick_provider,
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        self.memory_log = TradingMemoryLog(self.config)
        
        self.position_state = PositionStateManager(self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config["max_debate_rounds"],
            max_risk_discuss_rounds=self.config["max_risk_discuss_rounds"],
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.conditional_logic,
        )

        self.propagator = Propagator()
        self.reflector = Reflector(
            self.quick_thinking_llm,
            benchmark_name=self.config.get("benchmark_name", "沪深300"),
        )
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph: keep the workflow for recompilation with a checkpointer.
        self.workflow = self.graph_setup.setup_graph(
            selected_analysts,
            fan_out_enabled=self.config.get("fan_out_enabled", True),
        )
        self.graph = self.workflow.compile()
        self._checkpointer_ctx = None

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort

        elif provider == "anthropic":
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Current real-time price
                    get_current_price,
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                    # Market context (index, sector flow, breadth)
                    get_market_context,
                ]
            ),
            "social": ToolNode(
                [
                    # Social sentiment behavioral metrics (attention, hot ranking, etc.)
                    get_social_sentiment_tool,
                    # News tools for cross-validation
                    get_news,
                    # Real-time financial news flashes from 财联社
                    get_cls_flash,
                    # Hot stock reasons with theme/subject tags
                    get_hot_stock_reasons,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                ]
            ),
        }

    def _fetch_returns(
        self, ticker: str, trade_date: str, holding_days: int = 5
    ) -> Tuple[Optional[float], Optional[float], Optional[int]]:
        """Fetch raw and alpha return for ticker over holding_days from trade_date.

        Returns (raw_return, alpha_return, actual_holding_days) or
        (None, None, None) if price data is unavailable (too recent, delisted,
        or network error).
        """
        try:
            start = datetime.strptime(trade_date, "%Y-%m-%d")
            end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
            end_str = end.strftime("%Y-%m-%d")

            market_type = self.config.get("market_type", "US_STOCK")
            benchmark_ticker = self.config.get("benchmark_ticker", "SPY")

            if market_type == "A_SHARE":
                stock_closes = self._get_ashare_close_series(ticker, trade_date, end_str)
                bench_closes = self._get_ashare_benchmark_close_series(
                    benchmark_ticker, trade_date, end_str
                )
            else:
                stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
                benchmark = yf.Ticker(benchmark_ticker).history(start=trade_date, end=end_str)
                stock_closes = stock["Close"].values if len(stock) >= 2 else None
                bench_closes = benchmark["Close"].values if len(benchmark) >= 2 else None

            if stock_closes is None or bench_closes is None or len(stock_closes) < 2 or len(bench_closes) < 2:
                return None, None, None

            actual_days = min(holding_days, len(stock_closes) - 1, len(bench_closes) - 1)
            raw = float(
                (stock_closes[actual_days] - stock_closes[0])
                / stock_closes[0]
            )
            bench_ret = float(
                (bench_closes[actual_days] - bench_closes[0])
                / bench_closes[0]
            )
            alpha = raw - bench_ret
            return raw, alpha, actual_days
        except Exception as e:
            logger.warning(
                "Could not resolve outcome for %s on %s (will retry next run): %s",
                ticker, trade_date, e,
            )
            return None, None, None

    @staticmethod
    def _get_ashare_close_series(ticker: str, start_date: str, end_date: str):
        """Get closing price series for an A-share stock via cached OHLCV data."""
        from tradingagents.dataflows.akshare import _load_ohlcv_akshare
        import pandas as pd

        try:
            data = _load_ohlcv_akshare(ticker, end_date)
            if data is None or data.empty:
                return None
            # Filter to requested date range (data already sorted by Date)
            data = data[data["Date"] >= pd.Timestamp(start_date)]
            if data.empty:
                return None
            return data["Close"].values
        except Exception:
            return None

    @staticmethod
    def _get_ashare_benchmark_close_series(
        benchmark_ticker: str, start_date: str, end_date: str
    ):
        import akshare as ak
        import pandas as pd
        from datetime import date as dt_date
        from tradingagents.dataflows.cache import DataCache
        from tradingagents.default_config import DEFAULT_CONFIG

        if benchmark_ticker.startswith("000"):
            index_sym = f"sh{benchmark_ticker}"
        elif benchmark_ticker.startswith("399"):
            index_sym = f"sz{benchmark_ticker}"
        else:
            index_sym = f"sh{benchmark_ticker}"

        def _fetch_benchmark():
            df = ak.stock_zh_index_daily(symbol=index_sym)
            if df is None or df.empty:
                return pd.DataFrame()
            return df

        cache = DataCache(DEFAULT_CONFIG.get("data_cache_dir", "~/.tradingagents/cache"))
        df = cache.get_or_fetch(
            namespace="benchmark",
            key=f"{benchmark_ticker}_{start_date}_{end_date}.csv",
            fetcher=_fetch_benchmark,
        )

        if df is None or df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        sd = dt_date.fromisoformat(start_date)
        ed = dt_date.fromisoformat(end_date)
        df = df[(df["date"] >= sd) & (df["date"] <= ed)]
        if df.empty:
            return None

        df = df.sort_values("date")
        return df["close"].values

    def _resolve_pending_entries(self, ticker: str) -> None:
        """Resolve pending log entries for ticker at the start of a new run.

        Fetches returns for each same-ticker pending entry, generates reflections,
        then writes all updates in a single atomic batch write to avoid redundant I/O.
        Skips entries whose price data is not yet available (too recent or delisted).

        Trade-off: only same-ticker entries are resolved per run.  Entries for
        other tickers accumulate until that ticker is run again.
        """
        pending = [e for e in self.memory_log.get_pending_entries() if e["ticker"] == ticker]
        if not pending:
            return

        updates = []
        for entry in pending:
            raw, alpha, days = self._fetch_returns(ticker, entry["date"])
            if raw is None:
                continue  # price not available yet — try again next run
            reflection = self.reflector.reflect_on_final_decision(
                final_decision=entry.get("decision", ""),
                raw_return=raw,
                alpha_return=alpha,
            )
            updates.append({
                "ticker": ticker,
                "trade_date": entry["date"],
                "raw_return": raw,
                "alpha_return": alpha,
                "holding_days": days,
                "reflection": reflection,
            })

        if updates:
            self.memory_log.batch_update_with_outcomes(updates)

    def propagate(self, company_name, trade_date,
                  cost_price: float = 0.0,
                  quantity: int = 0,
                  position_opened_date: str = "",
                  display_name: str = "",
                  industry: str = ""):
        """Run the trading agents graph for a company on a specific date.

        When ``checkpoint_enabled`` is set in config, the graph is recompiled
        with a per-ticker SqliteSaver so a crashed run can resume from the last
        successful node on a subsequent invocation with the same ticker+date.
        """
        self.ticker = company_name

        # Resolve any pending memory-log entries for this ticker before the pipeline runs.
        self._resolve_pending_entries(company_name)

        # Load persisted position if user didn't provide new one
        if cost_price <= 0 and quantity <= 0:
            loaded = self.position_state.load(company_name)
            if loaded is not None:
                cost_price = loaded["cost_price"]
                quantity = loaded["quantity"]
                position_opened_date = loaded.get("opened_date", "")
                logger.info(
                    "Loaded persisted position for %s: cost=%.2f qty=%d",
                    company_name, cost_price, quantity,
                )

        # Store for later use in _run_graph
        self._pending_cost_price = cost_price
        self._pending_quantity = quantity
        self._pending_position_opened_date = position_opened_date
        self._pending_display_name = display_name
        self._pending_industry = industry

        # Reset incremental mode flags for each propagate() call
        self._incremental_mode = False
        self._recent_analyses = []

        # ★ Level 1: same ticker same day already analyzed?
        if self.config.get("skip_if_analyzed_today", False):
            from tradingagents.analysis_archive import AnalysisArchive
            archive = AnalysisArchive(self.config)
            entry_id = AnalysisArchive._build_entry_id(str(trade_date), "batch", company_name)
            cached = archive.get(entry_id)
            if cached:
                logger.info("[Cache L1] %s on %s already analyzed, returning cached", company_name, trade_date)
                cached_analysis = cached.get("analysis", {})
                decision = cached_analysis.get("final_decision", cached.get("decision", "Hold"))
                cached_state = {
                    "final_trade_decision": decision,
                    "company_of_interest": company_name,
                    "trade_date": str(trade_date),
                    "_cached": True,
                }
                return cached_state, decision

        # ★ Level 2: Recent analysis within window?
        incremental_days = self.config.get("incremental_window_days", 0)
        if incremental_days > 0:
            from tradingagents.analysis_archive import AnalysisArchive
            archive = AnalysisArchive(self.config)
            recent = archive.list(ticker=company_name, date_from=str(trade_date), limit=1)
            if recent:
                logger.info("[Cache L2] %s recent analysis found, incremental mode", company_name)
                self._incremental_mode = True
                self._recent_analyses = recent

        # Recompile with a checkpointer if the user opted in.
        if self.config.get("checkpoint_enabled"):
            self._checkpointer_ctx = get_checkpointer(
                self.config["data_cache_dir"], company_name
            )
            saver = self._checkpointer_ctx.__enter__()
            self.graph = self.workflow.compile(checkpointer=saver)

            step = checkpoint_step(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )
            if step is not None:
                logger.info(
                    "Resuming from step %d for %s on %s", step, company_name, trade_date
                )
            else:
                logger.info("Starting fresh for %s on %s", company_name, trade_date)

        try:
            result = self._run_graph(company_name, trade_date)

            # Post-analysis archive save
            if self.config.get("enable_archive_first_cache", True):
                try:
                    from cli.archive import save_to_archive
                    decision = result[1]
                    summary = result[0].get("final_trade_decision", "")
                    save_to_archive(
                        {"decision": decision, "summary": summary, "analysts": ["batch"]},
                        "batch", company_name, str(trade_date), self.config,
                    )
                except Exception as e:
                    logger.warning("Post-analysis archive save failed: %s", e)

            self._auto_update_position(
                company_name, str(trade_date),
                result[0]["final_trade_decision"],
                getattr(self, '_pending_cost_price', 0.0),
                getattr(self, '_pending_quantity', 0),
            )
            return result
        finally:
            if self._checkpointer_ctx is not None:
                self._checkpointer_ctx.__exit__(None, None, None)
                self._checkpointer_ctx = None
                self.graph = self.workflow.compile()

    def _run_graph(self, company_name, trade_date):
        """Execute the graph and write the resulting state to disk and memory log."""
        # Initialize state — inject memory log context for PM.
        past_context = self.memory_log.get_past_context(company_name)

        # Phase 1: Assemble knowledge context before graph execution.
        knowledge_context = {}
        if self.config.get("enable_context_assembly", True):
            try:
                from tradingagents.graph.context_assembly import ContextAssembler
                assembler = ContextAssembler(self.config)
                knowledge_context = assembler.assemble(
                    company_name, str(trade_date),
                    market_type=self.config.get("market_type", "A_SHARE"),
                )
                logger.info(
                    "Knowledge context assembled: %d archived, %d signals, %d lessons",
                    len(knowledge_context.get("archived_analyses", [])),
                    knowledge_context.get("ticker_signals", {}).get("total_entries", 0),
                    len(knowledge_context.get("lessons", [])),
                )
            except Exception as e:
                logger.warning("ContextAssembly failed for %s: %s", company_name, e)

        # ★ Phase 1.5: Market context assembly
        market_context = ""
        if self.config.get("enable_market_context", True):
            try:
                from tradingagents.dataflows.market_context import fetch_market_context
                from tradingagents.dataflows.cache import DataCache
                from tradingagents.default_config import DEFAULT_CONFIG

                mc_cache = DataCache(DEFAULT_CONFIG.get("data_cache_dir", "~/.tradingagents/cache"))
                mc_key = f"market_context_{str(trade_date)}.json"

                cached = mc_cache.get("market", mc_key)
                if cached is not None and isinstance(cached, dict):
                    market_context = cached.get("text", "")
                    logger.info(
                        "Market context cache HIT for %s on %s",
                        company_name, trade_date,
                    )
                else:
                    market_context = fetch_market_context(
                        str(trade_date),
                        market_type=self.config.get("market_type", "A_SHARE"),
                    )
                    mc_cache.set("market", mc_key, {"text": market_context})
                    logger.info(
                        "Market context assembled for %s on %s",
                        company_name, trade_date,
                    )
            except Exception as e:
                logger.warning(
                    "Market context fetch failed for %s on %s: %s",
                    company_name, trade_date, e,
                )
                market_context = ""  # Graceful degradation

        init_agent_state = self.propagator.create_initial_state(
            company_name, trade_date, past_context=past_context,
            knowledge_context=knowledge_context,
            cost_price=getattr(self, '_pending_cost_price', 0.0),
            quantity=getattr(self, '_pending_quantity', 0),
            position_opened_date=getattr(self, '_pending_position_opened_date', ''),
            display_name=getattr(self, '_pending_display_name', ''),
            industry=getattr(self, '_pending_industry', ''),
        )

        # ★ Inject market context into agent state
        if market_context:
            init_agent_state["market_context"] = market_context

        # Inject incremental mode context into agent state
        if getattr(self, '_incremental_mode', False):
            init_agent_state["_incremental_mode"] = True
            init_agent_state["_recent_analyses"] = self._recent_analyses
            logger.info("Injected incremental context for %s into agent state", company_name)

        # Compute A-share limit up/down prices and inject into initial state.
        # Limit is based on the PREVIOUS trading day's close price.
        if self.config.get("market_type") == "A_SHARE":
            try:
                from tradingagents.dataflows.a_share_constraints import get_limit_prices
                from tradingagents.dataflows.akshare import _load_ohlcv_akshare
                from datetime import datetime
                import pandas as pd

                td = datetime.strptime(str(trade_date), "%Y-%m-%d")
                prev_close = None

                ohlcv_data = _load_ohlcv_akshare(company_name, str(trade_date))
                if ohlcv_data is not None and not ohlcv_data.empty:
                    trade_dt = pd.Timestamp(trade_date)
                    before_trade = ohlcv_data[ohlcv_data["Date"] < trade_dt]
                    if not before_trade.empty:
                        prev_close = float(before_trade["Close"].iloc[-1])

                if prev_close is not None:
                    limit_up, limit_down = get_limit_prices(company_name, prev_close)
                    init_agent_state["limit_up_price"] = limit_up
                    init_agent_state["limit_down_price"] = limit_down
                    init_agent_state["current_price"] = prev_close
                    init_agent_state["market_type"] = "A_SHARE"
                    logger.info(
                        "A-share limits for %s: up=%.2f down=%.2f (prev_close=%.2f)",
                        company_name, limit_up, limit_down, prev_close,
                    )
            except Exception as e:
                logger.warning("Could not compute limit prices for %s: %s", company_name, e)
        else:
            init_agent_state["market_type"] = "US_STOCK"

        args = self.propagator.get_graph_args()

        # Inject thread_id so same ticker+date resumes, different date starts fresh.
        if self.config.get("checkpoint_enabled"):
            tid = thread_id(company_name, str(trade_date))
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        if self.debug:
            trace = []
            for chunk in self.graph.stream(init_agent_state, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)
            final_state = trace[-1]
        else:
            final_state = self.graph.invoke(init_agent_state, **args)

        # Store current state for reflection.
        self.curr_state = final_state

        # Log state to disk.
        self._log_state(trade_date, final_state)

        # ★ FIX-10: Causal trace — record (decision, basis, source) triples
        if self.config.get("enable_causal_trace", True):
            try:
                from tradingagents.graph.causal_tracer import (
                    CausalTracer,
                    build_trace_from_state,
                )
                tracer = CausalTracer(f"{company_name}:{trade_date}")
                build_trace_from_state(tracer, final_state, self.quick_thinking_llm)

                safe_ticker = safe_ticker_component(company_name)
                trace_dir = Path(self.config["results_dir"]) / safe_ticker / "traces"
                tracer.save(trace_dir, str(trade_date))
            except Exception as e:
                logger.warning(
                    "Causal trace failed for %s on %s: %s",
                    company_name, trade_date, e,
                )

        # Store decision for deferred reflection on the next same-ticker run.
        self.memory_log.store_decision(
            ticker=company_name,
            trade_date=trade_date,
            final_trade_decision=final_state["final_trade_decision"],
        )

        # Clear checkpoint on successful completion to avoid stale state.
        if self.config.get("checkpoint_enabled"):
            clear_checkpoint(
                self.config["data_cache_dir"], company_name, str(trade_date)
            )

        return final_state, self.process_signal(final_state["final_trade_decision"])

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
            },
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file. Reject ticker values that would escape the
        # results directory when joined as a path component.
        safe_ticker = safe_ticker_component(self.ticker)
        directory = Path(self.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        directory.mkdir(parents=True, exist_ok=True)

        log_path = directory / f"full_states_log_{trade_date}.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(self.log_states_dict[str(trade_date)], f, indent=4)

    def build_report(self, final_state: dict) -> str:
        """Build a clean Markdown report from the final agent state.

        Replaces the deleted ReportRenderer — simple concatenation,
        no regex parsing, no risk of table corruption.
        """
        parts = []

        # P-新A: show industry analysis framework in report header
        industry = final_state.get("industry", "")
        if industry:
            anti_patterns: list[str] = []
            try:
                from tradingagents.industry.frameworks import IndustryFramework
                framework = IndustryFramework().lookup(industry)
                if framework:
                    anti_patterns = framework.get("anti_patterns", [])
            except Exception:
                pass
            header = f"## 🎯 行业分析框架\n\n**行业分类**: {industry}\n"
            if anti_patterns:
                header += f"**禁止使用术语**: {'、'.join(anti_patterns)}\n"
            parts.append(header)

        for title, state_key in [
            ("Market Analyst", "market_report"),
            ("Fundamentals Analyst", "fundamentals_report"),
            ("News Analyst", "news_report"),
            ("Sentiment Analyst", "sentiment_report"),
        ]:
            content = final_state.get(state_key, "")
            if content:
                parts.append(f"--- {title} ---\n\n{content}")

        investment_plan = final_state.get("investment_plan", "")
        if investment_plan:
            parts.append(f"--- Investment Plan ---\n\n{investment_plan}")

        trader_plan = final_state.get("trader_investment_plan", "")
        if trader_plan:
            parts.append(f"--- Trader Plan ---\n\n{trader_plan}")

        final_decision = final_state.get("final_trade_decision", "")
        if final_decision and final_decision != investment_plan:
            parts.append(f"--- Final Decision ---\n\n{final_decision}")

        return "\n\n".join(parts) if parts else ""

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)

    def _auto_update_position(self, ticker: str, trade_date: str,
                              final_decision: str, cost_price: float,
                              quantity: int) -> None:
        """Auto-update simulated position based on final decision."""
        market_type = self.config.get("market_type", "A_SHARE")
        if market_type != "A_SHARE":
            return

        existing = self.position_state.load(ticker)
        if existing and existing.get("updated_at", "").startswith(trade_date):
            logger.info("Skipping auto-update for %s on %s (already updated)", ticker, trade_date)
            return

        rating = parse_rating(final_decision)

        if rating in ("Buy", "Overweight"):
            if quantity == 0:
                close_price = self._get_analysis_day_close(ticker, trade_date)
                if close_price is not None:
                    self.position_state.save(ticker, close_price, 100, trade_date)
                    logger.info("Auto-opened position for %s at %.2f", ticker, close_price)

        elif rating in ("Sell", "Underweight"):
            if quantity > 0:
                from tradingagents.dataflows.a_share_constraints import format_t_plus_1_constraint
                existing = self.position_state.load(ticker)
                if existing:
                    opened = existing.get("opened_date", "")
                    t1_check = format_t_plus_1_constraint(opened, trade_date, "A_SHARE")
                    if "T+1" in t1_check and "CANNOT" in t1_check.upper():
                        logger.info("T+1 blocks sell for %s (opened %s)", ticker, opened)
                        return
                    close_price = self._get_analysis_day_close(ticker, trade_date)
                    if close_price is not None:
                        self.position_state.reset(ticker)
                        logger.info("Auto-closed position for %s at %.2f", ticker, close_price)

    def _get_analysis_day_close(self, ticker: str, trade_date: str) -> Optional[float]:
        try:
            from tradingagents.dataflows.akshare import _load_ohlcv_akshare
            import pandas as pd

            data = _load_ohlcv_akshare(ticker, trade_date)
            if data is None or data.empty:
                return None

            target = pd.Timestamp(trade_date)
            matching = data[data["Date"] == target]
            if matching.empty:
                return None
            return float(matching["Close"].iloc[0])
        except Exception as e:
            logger.warning("Could not get close price for %s on %s: %s", ticker, trade_date, e)
            return None
