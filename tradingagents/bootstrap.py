"""Bootstrap — wires up all V1.2 components at service startup.

Called by api_server.py's startup event (or on first request in lazy mode).
Creates LLM clients, tool nodes, KB, Planner, Executor, Scheduler.
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv

from .default_config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)

_initialized = False


def bootstrap(env_file: str = ".env"):
    global _initialized
    if _initialized:
        return
    _initialized = True

    load_dotenv(env_file)
    load_dotenv(".env.enterprise", override=False)

    config = DEFAULT_CONFIG.copy()
    config = _apply_env_overrides(config)

    deep_llm, quick_llm = _create_llms(config)
    if not deep_llm or not quick_llm:
        logger.warning("LLM clients unavailable — planner and executor disabled")
        return None
    tool_nodes = _create_tool_nodes()

    from .planner.llm_planner import LLMPlanner
    from .kb.knowledge_base import KnowledgeBase
    from .graph.executor import GraphExecutor

    kb = KnowledgeBase()
    planner = LLMPlanner(kb=kb, llm=quick_llm)
    executor = GraphExecutor(
        quick_thinking_llm=quick_llm,
        deep_thinking_llm=deep_llm,
        tool_nodes=tool_nodes,
        max_debate_rounds=config.get("max_debate_rounds", 1),
        max_risk_rounds=config.get("max_risk_discuss_rounds", 1),
        max_recur_limit=config.get("max_recur_limit", 100),
        fan_out_enabled=config.get("fan_out_enabled", True),
        enable_checkpoint=config.get("enable_checkpoint", False),
        data_dir=config.get("data_cache_dir", "~/.tradingagents/cache"),
    )

    from .portfolio.portfolio_manager import PortfolioManager
    portfolio_mgr = PortfolioManager()

    from .dashboard.cost_tracker import CostTracker
    cost_tracker = CostTracker()

    from .api_server import configure
    configure(planner, executor, portfolio_mgr, kb, cost_tracker)

    try:
        _start_scheduler(kb, planner, portfolio_mgr, executor, config)
    except RuntimeError as e:
        logger.warning("Scheduler skipped (no event loop): %s", e)
    _start_dashboard(kb, config)

    logger.info("Bootstrap complete — API server ready")
    return planner, executor, kb, portfolio_mgr


def _apply_env_overrides(config: dict) -> dict:
    for key in ("llm_provider", "deep_think_llm", "quick_think_llm", "backend_url"):
        env_key = f"TRADINGAGENTS_{key.upper()}"
        if os.getenv(env_key):
            config[key] = os.getenv(env_key)
    fan_out_env = os.getenv("TRADINGAGENTS_FAN_OUT")
    if fan_out_env and fan_out_env.lower() == "true":
        config["fan_out_enabled"] = True
        logger.info("Fan-out enabled via TRADINGAGENTS_FAN_OUT=true")
    if os.getenv("OPENAI_API_KEY"):
        config.setdefault("llm_provider", "openai")
    if os.getenv("DEEPSEEK_API_KEY"):
        config.setdefault("llm_provider", "deepseek")
    return config


def _create_llms(config: dict):
    from .llm_clients import create_llm_client
    from .llm_clients.validators import validate_model

    llm_kwargs = {}
    provider = config.get("llm_provider", "").lower()

    deep_model = config.get("deep_think_llm", "")
    quick_model = config.get("quick_think_llm", "")
    if not validate_model(provider, deep_model):
        logger.warning(
            "deep_think_llm '%s' is not in the known model list for provider '%s'. Continuing anyway.",
            deep_model, provider,
        )
    if not validate_model(provider, quick_model):
        logger.warning(
            "quick_think_llm '%s' is not in the known model list for provider '%s'. Continuing anyway.",
            quick_model, provider,
        )

    if provider == "google":
        if config.get("google_thinking_level"):
            llm_kwargs["thinking_level"] = config["google_thinking_level"]
    elif provider == "openai":
        if config.get("openai_reasoning_effort"):
            llm_kwargs["reasoning_effort"] = config["openai_reasoning_effort"]
    elif provider == "anthropic":
        if config.get("anthropic_effort"):
            llm_kwargs["effort"] = config["anthropic_effort"]

    try:
        deep_client = create_llm_client(
            provider=config["llm_provider"],
            model=config["deep_think_llm"],
            base_url=config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=config["llm_provider"],
            model=config["quick_think_llm"],
            base_url=config.get("backend_url"),
            **llm_kwargs,
        )
    except Exception as e:
        logger.warning("LLM client creation failed (missing API key?): %s", e)
        return None, None

    deep_llm = deep_client.get_llm()
    quick_llm = quick_client.get_llm()

    # FIX-4: wrap deep_llm with automatic retry + fallback to quick_llm
    from .llm_clients.resilient_llm import ResilientLLM
    resilient_deep = ResilientLLM(
        primary=deep_llm,
        fallback=quick_llm,
        max_retries=2,
        retry_delay=3.0,
    )
    return resilient_deep, quick_llm


def _create_tool_nodes():
    from langgraph.prebuilt import ToolNode

    from .agents.utils.agent_utils import (
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
    from .agents.utils.social_sentiment_tools import get_social_sentiment_tool
    from .agents.utils.a_stock_data_tools import (
        get_cls_flash, get_hot_stock_reasons, get_margin_trading,
        get_institutional_holdings,
    )

    return {
        "market": ToolNode([
            get_current_price,
            get_stock_data,
            get_indicators,
            get_market_context,
        ]),
        "social": ToolNode([
            get_social_sentiment_tool,
            get_news,
            get_cls_flash,
            get_hot_stock_reasons,
        ]),
        "news": ToolNode([
            get_news,
            get_global_news,
            get_insider_transactions,
        ]),
        "fundamentals": ToolNode([
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_margin_trading,
            get_institutional_holdings,
        ]),
    }


def _start_scheduler(kb, planner, portfolio_mgr, executor, config):
    from .scheduler.scheduler import TradingAgentsScheduler
    from .notifier import OpenClawPushClient

    openclaw = OpenClawPushClient()
    if not openclaw.configured:
        openclaw = None
        logger.info("OpenClaw push not configured (set OPENCLAW_URL + OPENCLAW_HOOK_TOKEN to enable)")

    scheduler = TradingAgentsScheduler(
        kb=kb,
        planner=planner,
        portfolio_mgr=portfolio_mgr,
        executor=executor,
        openclaw=openclaw,
        config=config,
    )
    scheduler.start()
    logger.info("Scheduler started (collectors + events)")


def _start_dashboard(kb, config):
    dashboard_enabled = os.getenv("TRADINGAGENTS_DASHBOARD", "0") == "1"
    if not dashboard_enabled:
        return
    try:
        from .dashboard.user_dashboard import UserDashboard
        dashboard = UserDashboard(
            portfolio_mgr=None,
            kb=kb,
            archive=None,
            base_dir=config.get("data_cache_dir", "~/.tradingagents"),
        )
        logger.info("Dashboard initialized")
    except Exception:
        logger.warning("Dashboard init failed (non-blocking)")


def lazy_bootstrap():
    global _initialized
    if not _initialized:
        return bootstrap()
    return None
