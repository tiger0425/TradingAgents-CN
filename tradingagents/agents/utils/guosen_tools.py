"""Guosen Securities unique tool wrappers for TradingAgents.

这些工具仅通过国信证券接口提供，akshare/yfinance 等常规数据商不支持。
所有函数通过 interface.route_to_vendor() 路由到 guosen vendor。
"""

from typing import Annotated, Optional
from tradingagents.dataflows.interface import route_to_vendor


def get_macro_data(
    query: Annotated[str, "自然语言查询，如 '中国近五年GDP同比增速'，'美国最新CPI'，'WTI原油价格走势'"],
) -> str:
    """查询宏观经济数据 (GDP/CPI/PMI/利率/汇率/大宗商品)。

    覆盖中国及全球主要经济体。支持自然语言描述，无需精确指标名。
    """
    return route_to_vendor("get_macro_data", query)


def screen_stocks(
    conditions: Annotated[str, "选股条件，如 '市盈率小于20的银行股'"],
    search_type: Annotated[str, "类型: stock(默认)/fund/HK_stock/US_stock/NEEQ/index"] = "stock",
) -> str:
    """根据财务/技术指标筛选股票。

    支持市盈率、市净率、净利润、均线、MACD、KDJ、市值、行业等条件组合。
    """
    return route_to_vendor("screen_stocks", conditions, search_type)


def get_rankings(
    set_domain: Annotated[int, "查询类型: 0-上证A股, 2-深证A股, 6-沪深A股(默认)"] = 6,
    want_num: Annotated[int, "返回数量 (最多80)"] = 10,
    sort_type: Annotated[int, "排序: 1-涨幅, 2-跌幅"] = 1,
) -> str:
    """查询涨跌幅排名。"""
    return route_to_vendor("get_rankings", set_domain, want_num, sort_type)


def get_fund_flow(
    symbol: Annotated[str, "A股6位代码"],
    period: Annotated[int, "查询周期(日)，最多60日"] = 60,
) -> str:
    """查询个股资金流向，包括主力/大户/散户资金进出。仅支持沪深市场。"""
    return route_to_vendor("get_fund_flow", symbol, period)


def get_multi_quote(
    symbols: Annotated[str, "股票代码列表，逗号分隔 (如 '600519,000858')"],
) -> str:
    """批量查询多只证券实时行情，单次最多10只。"""
    return route_to_vendor("get_multi_quote", symbols)


def compare_funds(
    fund_codes: Annotated[str, "基金代码，逗号分隔 (如 '000001,161039')，2-4只"],
) -> str:
    """对比场外基金多维度数据：业绩、风控、资产配置、基金经理、费率。"""
    return route_to_vendor("compare_funds", fund_codes)


def filter_etf_pro(
    class_id: Annotated[int, "榜单分类: 1-短线热榜, 2-中长期精选, 3-特色品种"],
    list_id: Annotated[int, "榜单ID (见文档映射表)"],
) -> str:
    """使用专业榜单筛选ETF (如 filter_etf_pro(2,21) → 高分红低波动)。"""
    return route_to_vendor("filter_etf_pro", class_id, list_id)


def filter_etf_custom(
    class1: Annotated[Optional[str], "一级类型: 1-行业, 2-宽基, 3-风格策略, 4-跨境, 5-债券, 6-黄金, 7-货币"] = None,
    endamt: Annotated[Optional[str], "规模区间(亿): 如 '10,50' 表示10-50亿"] = None,
    is_t0: Annotated[bool, "是否 T+0"] = False,
    **kwargs: str,
) -> str:
    """自定义多维条件筛选ETF。支持7大维度24个指标。"""
    return route_to_vendor("filter_etf_custom", class1, endamt, is_t0, **kwargs)
