from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .akshare import (
    get_stock_data as get_akshare_stock,
    get_indicators as get_akshare_indicators,
    get_fundamentals as get_akshare_fundamentals,
    get_balance_sheet as get_akshare_balance_sheet,
    get_cashflow as get_akshare_cashflow,
    get_income_statement as get_akshare_income_statement,
    get_news as get_akshare_news,
    get_global_news as get_akshare_global_news,
    get_insider_transactions as get_akshare_insider_transactions,
    get_current_price as get_akshare_current_price,
)
from .guosen import (
    get_real_time_quote,
    get_multi_quote,
    get_fund_flow,
    get_rankings,
    get_historical_hq,
    get_balance_sheet as guosen_balance_sheet,
    get_income_statement as guosen_income_statement,
    get_cashflow_statement as guosen_cashflow,
    get_macro_data,
    screen_stocks,
    compare_funds,
    filter_etf_pro,
    filter_etf_custom,
)
from .a_stock_data import (
    get_dragon_tiger_stock,
    get_dragon_tiger_market,
    get_margin_trading,
    get_block_trade,
    get_lockup_expiry,
    get_shareholder_count,
    get_dividend_history,
    get_cls_flash,
    get_cninfo_announcements,
)
from .alpha_vantage_common import AlphaVantageRateLimitError

# Configuration and routing logic
from .config import get_config


# ---- Guosen adapter wrappers (unify signatures with standard tool interface) ----

def _guosen_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Adapt guosen get_historical_hq to standard (symbol, start, end) signature."""
    from datetime import datetime
    try:
        d1 = datetime.strptime(start_date, "%Y-%m-%d")
        d2 = datetime.strptime(end_date, "%Y-%m-%d")
        days = max((d2 - d1).days, 1)
    except (ValueError, TypeError):
        days = 20
    return get_historical_hq(symbol, days=days)


def _guosen_current_price(symbol: str) -> str:
    """Adapt guosen get_real_time_quote to standard current_price signature."""
    return get_real_time_quote(symbol)


def _guosen_bs(ticker: str, freq: str = "annual", curr_date: str = "") -> str:
    """Adapt guosen balance_sheet to standard (ticker, freq, curr_date) signature."""
    report_map = {"annual": "Q4", "quarterly": "Q0"}
    rtype = report_map.get(freq, "Q0")
    year = curr_date[:4] if curr_date else None
    return guosen_balance_sheet(ticker, report_type=rtype, report_year=year)


def _guosen_cf(ticker: str, freq: str = "annual", curr_date: str = "") -> str:
    """Adapt guosen cashflow to standard (ticker, freq, curr_date) signature."""
    report_map = {"annual": "Q4", "quarterly": "Q0"}
    rtype = report_map.get(freq, "Q0")
    year = curr_date[:4] if curr_date else None
    return guosen_cashflow(ticker, report_type=rtype, report_year=year)


def _guosen_is_(ticker: str, freq: str = "annual", curr_date: str = "") -> str:
    """Adapt guosen income_statement to standard (ticker, freq, curr_date) signature."""
    report_map = {"annual": "Q4", "quarterly": "Q0"}
    rtype = report_map.get(freq, "Q0")
    year = curr_date[:4] if curr_date else None
    return guosen_income_statement(ticker, report_type=rtype, report_year=year)


# ---- Tool categories (extended with guosen-unique capabilities) ----

TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data and real-time quotes",
        "tools": [
            "get_stock_data",
            "get_current_price",
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    },
    # ---- Guosen 独有能力 ----
    "macro_economic": {
        "description": "Macroeconomic indicators (GDP, CPI, PMI, interest rates, commodities)",
        "tools": ["get_macro_data"],
    },
    "stock_screening": {
        "description": "Stock screening by financial/technical conditions and ETF/fund filters",
        "tools": [
            "screen_stocks",
            "get_rankings",
            "get_fund_flow",
            "get_multi_quote",
            "compare_funds",
            "filter_etf_pro",
            "filter_etf_custom",
        ],
    },
    "specialty_data": {
        "description": "A股特色数据（龙虎榜/融资融券/大宗交易/解禁/股东户数/分红/快讯/公告）",
        "tools": [
            "get_dragon_tiger_stock", "get_dragon_tiger_market",
            "get_margin_trading", "get_block_trade", "get_lockup_expiry",
            "get_shareholder_count", "get_dividend_history",
            "get_cls_flash", "get_cninfo_announcements",
        ],
    },
}

VENDOR_LIST = [
    "akshare",
    "yfinance",
    "alpha_vantage",
    "guosen",
    "a_stock_data",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "akshare": get_akshare_stock,
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
        "guosen": _guosen_stock_data,
    },
    "get_current_price": {
        "akshare": get_akshare_current_price,
        "yfinance": get_YFin_data_online,
        "guosen": _guosen_current_price,
    },
    # technical_indicators
    "get_indicators": {
        "akshare": get_akshare_indicators,
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "akshare": get_akshare_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "akshare": get_akshare_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
        "guosen": _guosen_bs,
    },
    "get_cashflow": {
        "akshare": get_akshare_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
        "guosen": _guosen_cf,
    },
    "get_income_statement": {
        "akshare": get_akshare_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
        "guosen": _guosen_is_,
    },
    # news_data
    "get_news": {
        "akshare": get_akshare_news,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "akshare": get_akshare_global_news,
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "akshare": get_akshare_insider_transactions,
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
    # ---- guosen 独有能力 (仅 guosen vendor 提供) ----
    "get_macro_data": {
        "guosen": get_macro_data,
    },
    "screen_stocks": {
        "guosen": screen_stocks,
    },
    "get_rankings": {
        "guosen": get_rankings,
    },
    "get_fund_flow": {
        "guosen": get_fund_flow,
    },
    "get_multi_quote": {
        "guosen": get_multi_quote,
    },
    "compare_funds": {
        "guosen": compare_funds,
    },
    "filter_etf_pro": {
        "guosen": filter_etf_pro,
    },
    "filter_etf_custom": {
        "guosen": filter_etf_custom,
    },
    # === a-stock-data 独有能力 ===
    "get_dragon_tiger_stock": {"a_stock_data": get_dragon_tiger_stock},
    "get_dragon_tiger_market": {"a_stock_data": get_dragon_tiger_market},
    "get_margin_trading": {"a_stock_data": get_margin_trading},
    "get_block_trade": {"a_stock_data": get_block_trade},
    "get_lockup_expiry": {"a_stock_data": get_lockup_expiry},
    "get_shareholder_count": {"a_stock_data": get_shareholder_count},
    "get_dividend_history": {"a_stock_data": get_dividend_history},
    "get_cls_flash": {"a_stock_data": get_cls_flash},
    "get_cninfo_announcements": {"a_stock_data": get_cninfo_announcements},
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    primary_vendors = [v.strip() for v in vendor_config.split(',')]

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    # Build fallback chain: primary vendors first, then remaining available vendors
    all_available_vendors = list(VENDOR_METHODS[method].keys())
    fallback_vendors = primary_vendors.copy()
    for vendor in all_available_vendors:
        if vendor not in fallback_vendors:
            fallback_vendors.append(vendor)

    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        try:
            return impl_func(*args, **kwargs)
        except AlphaVantageRateLimitError:
            continue  # Only rate limits trigger fallback

    raise RuntimeError(f"No available vendor for '{method}'")