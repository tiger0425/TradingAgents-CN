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
    from .default_config import apply_env_overrides
    config = apply_env_overrides(config)

    from .kb.knowledge_base import KnowledgeBase
    from .graph.trading_graph import TradingAgentsGraph

    kb = KnowledgeBase()
    executor = TradingAgentsGraph(
        debug=False,
        config=config,
    )

    from .portfolio.portfolio_manager import PortfolioManager
    portfolio_mgr = PortfolioManager()

    from .dashboard.cost_tracker import CostTracker
    cost_tracker = CostTracker()

    from .api_server import configure
    configure(trading_graph=executor, portfolio_mgr=portfolio_mgr,
              kb=kb, cost_tracker=cost_tracker)

    try:
        _start_scheduler(kb, None, portfolio_mgr, executor, config)
    except RuntimeError as e:
        logger.warning("Scheduler skipped (no event loop): %s", e)
    _start_dashboard(kb, config)

    logger.info("Bootstrap complete — API server ready")
    return None, executor, kb, portfolio_mgr  # planner slot None until Wave 4 removes callers


def _create_llms(config: dict):
    from .llm_clients import create_llm_client
    from .llm_clients.validators import validate_model

    llm_kwargs = {
        "temperature": config.get("llm_temperature", 0.0),
        "max_tokens": config.get("llm_max_tokens", 4096),
    }
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

    quick_provider = os.getenv("TRADINGAGENTS_QUICK_LLM_PROVIDER") or config["llm_provider"]
    quick_model = config["quick_think_llm"]
    backend_url = config.get("backend_url")

    try:
        deep_client = create_llm_client(
            provider=config["llm_provider"],
            model=config["deep_think_llm"],
            base_url=backend_url,
            **llm_kwargs,
        )
        # Base quick client (temperature=0.0) for analyst
        quick_client = create_llm_client(
            provider=quick_provider,
            model=quick_model,
            base_url=backend_url,
            **llm_kwargs,
        )
        # Role-specific quick clients with differentiated temperatures
        debate_kwargs = {**llm_kwargs, "temperature": config.get("llm_debate_temperature", 0.3)}
        debate_client = create_llm_client(
            provider=quick_provider,
            model=quick_model,
            base_url=backend_url,
            **debate_kwargs,
        )
        risk_kwargs = {**llm_kwargs, "temperature": config.get("llm_risk_temperature", 0.2)}
        risk_client = create_llm_client(
            provider=quick_provider,
            model=quick_model,
            base_url=backend_url,
            **risk_kwargs,
        )
        decision_kwargs = {**llm_kwargs, "temperature": config.get("llm_decision_temperature", 0.1)}
        decision_client = create_llm_client(
            provider=quick_provider,
            model=quick_model,
            base_url=backend_url,
            **decision_kwargs,
        )
    except Exception as e:
        logger.warning("LLM client creation failed (missing API key?): %s", e)
        return None

    deep_llm = deep_client.get_llm()
    analyst_llm = quick_client.get_llm()
    debate_llm = debate_client.get_llm()
    risk_llm = risk_client.get_llm()
    decision_llm = decision_client.get_llm()

    # FIX-4: wrap deep_llm with automatic retry + fallback to analyst_llm
    from .llm_clients.resilient_llm import ResilientLLM
    resilient_deep = ResilientLLM(
        primary=deep_llm,
        fallback=analyst_llm,
        max_retries=2,
        retry_delay=3.0,
    )
    return {
        "analyst": analyst_llm,
        "debate": debate_llm,
        "risk": risk_llm,
        "decision": decision_llm,
        "deep": resilient_deep,
    }


def _create_tool_nodes():
    """Legacy — TradingAgentsGraph creates its own tool nodes."""
    from langgraph.prebuilt import ToolNode

    from .agents.utils.agent_utils import (
        get_stock_data,
        get_current_price,
        get_indicators,
        get_fundamentals,
        get_news,
        get_global_news,
        get_market_context,
    )
    from .agents.utils.social_sentiment_tools import get_social_sentiment_tool
    from .agents.utils.a_stock_data_tools import (
        get_cls_flash, get_hot_stock_reasons,
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
        ]),
        "fundamentals": ToolNode([
            get_fundamentals,
        ]),
    }
    from langgraph.prebuilt import ToolNode

    from .agents.utils.agent_utils import (
        get_stock_data,
        get_current_price,
        get_indicators,
        get_fundamentals,
        get_news,
        get_global_news,
        get_market_context,
    )
    from .agents.utils.social_sentiment_tools import get_social_sentiment_tool
    from .agents.utils.a_stock_data_tools import (
        get_cls_flash, get_hot_stock_reasons,
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
        ]),
        "fundamentals": ToolNode([
            get_fundamentals,
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
