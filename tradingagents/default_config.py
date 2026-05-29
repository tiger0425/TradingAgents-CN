import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "deepseek-v4-pro",
    "quick_think_llm": "deepseek-v4-flash",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # V1.2 GraphExecutor checkpoint (separate from legacy trading_graph path).
    # When True, GraphExecutor saves/restores state via task-based SQLite DB.
    # Default off for gradual rollout. See tradingagents/graph/executor.py.
    "enable_checkpoint": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "Chinese",
    # FIX-1: 分析师并行化 — 扇出-汇聚并行模式开关
    # true: 4 个分析师通过 LangGraph Send API 并行执行 (~90s 总耗时)
    # false: 回退串行模式 (~270s 总耗时)
    "fan_out_enabled": False,
    # Debate and discussion settings
    "max_debate_rounds": 2,
    "max_risk_discuss_rounds": 2,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "akshare",       # Options: akshare, guosen, alpha_vantage, yfinance
        "technical_indicators": "akshare",  # Options: akshare, alpha_vantage, yfinance (guosen 不支持)
        "fundamental_data": "akshare",      # Options: akshare, guosen, alpha_vantage, yfinance
        "news_data": "akshare",             # Options: akshare, alpha_vantage, yfinance (guosen 不支持)
        "macro_economic": "guosen",         # 宏观经济数据 (仅 guosen)
        "stock_screening": "guosen",        # 选股/ETF筛选/基金对比/排行 (仅 guosen)
    },
    # Benchmark index for alpha calculation
    "benchmark_ticker": "000300",       # A-share: 沪深300 CSI 300 index
    "benchmark_name": "沪深300",
    # Market type: "A_SHARE" or "US_STOCK"
    "market_type": "A_SHARE",
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },

    # ============================================================
    # Knowledge Consumption Config (Phase 0-5)
    # ============================================================
    # Token budget for history knowledge injection
    "knowledge_token_budget": 25000,
    # Skip analysis if same ticker already analyzed today
    "skip_if_analyzed_today": False,
    # Incremental analysis window in days (0 = disabled)
    "incremental_window_days": 0,
    # Enable ContextAssembly at run start
    "enable_context_assembly": True,
    # Enable archive-first cache for data fetching
    "enable_archive_first_cache": True,
    # Market context injection switch
    "enable_market_context": True,

    # Causal trace — logs (decision, basis, source) triples for each agent node
    "enable_causal_trace": True,

    # Confidence tags
    "confidence_tags_enabled": True,
    # Threshold: CONFIRMED > SINGLE > DERIVED > CONFLICTING > STALE
    # Conclusions below this confidence are filtered from prompt injection
    "confidence_threshold_inject": "CONFLICTING",

    # Graphify integration
    "graphify_auto_sync": True,
    "graphify_analysis_graph_path": "",

    # MCP Server
    "mcp_server_enabled": False,
    "mcp_server_port": 8765,

    # Wiki generator
    "wiki_output_dir": "~/.tradingagents/wiki/",
    "wiki_auto_generate": False,

    # Analysis archive dir (for cache triple-check chain)
    "analysis_archive_dir": os.path.join(_TRADINGAGENTS_HOME, "analysis-archive"),
}
