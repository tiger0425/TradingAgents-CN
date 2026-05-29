"""A股特色数据 LangChain Tool 包装器。

所有函数通过 interface.route_to_vendor() 路由到 a_stock_data vendor。
数据来源：东方财富 datacenter-web HTTP API + 财联社直连 + 巨潮公告接口。
"""

from typing import Annotated

from langchain_core.tools import tool
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_dragon_tiger_stock(
    code: Annotated[str, "A股6位代码，如 600519"],
    trade_date: Annotated[str, "交易日期，格式 YYYY-MM-DD"],
    look_back: Annotated[int, "向前回溯天数，默认30"] = 30,
) -> str:
    """查询个股龙虎榜上榜记录及买卖席位，包含近N天上榜记录、买入/卖出席位TOP5及机构席位标记。"""
    return route_to_vendor("get_dragon_tiger_stock", code=code, trade_date=trade_date, look_back=look_back)


@tool
def get_dragon_tiger_market(
    trade_date: Annotated[str, "交易日期（YYYY-MM-DD），默认当天"] = "",
    min_net_buy: Annotated[float, "最小净买入（万元），默认0"] = 0,
) -> str:
    """查询全市场龙虎榜，按净买入金额降序排列，支持按最小净买入金额过滤。"""
    return route_to_vendor("get_dragon_tiger_market", trade_date=trade_date, min_net_buy=min_net_buy)


@tool
def get_margin_trading(
    code: Annotated[str, "A股6位代码，如 600519"],
    page_size: Annotated[int, "返回条数，默认30"] = 30,
) -> str:
    """查询个股融资融券明细（日级），返回近N天融资余额/融券余额/两融合计数据。"""
    return route_to_vendor("get_margin_trading", code=code, page_size=page_size)


@tool
def get_block_trade(
    code: Annotated[str, "A股6位代码，如 600519"],
    page_size: Annotated[int, "返回条数，默认20"] = 20,
) -> str:
    """查询个股大宗交易记录，包含成交价/收盘价/溢价率/成交量/买卖方营业部。"""
    return route_to_vendor("get_block_trade", code=code, page_size=page_size)


@tool
def get_lockup_expiry(
    code: Annotated[str, "A股6位代码，如 600519"],
    trade_date: Annotated[str, "基准交易日，格式 YYYY-MM-DD"],
    forward_days: Annotated[int, "未来预警天数，默认90"] = 90,
) -> str:
    """查询限售解禁日历，返回历史解禁记录 + 未来N天待解禁预警。"""
    return route_to_vendor("get_lockup_expiry", code=code, trade_date=trade_date, forward_days=forward_days)


@tool
def get_shareholder_count(
    code: Annotated[str, "A股6位代码，如 600519"],
    page_size: Annotated[int, "返回期数，默认10"] = 10,
) -> str:
    """查询股东户数变化趋势，包含每期股东户数、环比变化、户均持股及筹码集中度标记。"""
    return route_to_vendor("get_shareholder_count", code=code, page_size=page_size)


@tool
def get_dividend_history(
    code: Annotated[str, "A股6位代码，如 600519"],
    page_size: Annotated[int, "返回条数，默认30"] = 30,
) -> str:
    """查询分红送转历史，包含报告期、每股派息、送股、转增、进度状态。"""
    return route_to_vendor("get_dividend_history", code=code, page_size=page_size)


@tool
def get_cls_flash(
    count: Annotated[int, "返回条数，默认20"] = 20,
) -> str:
    """查询财联社实时快讯，返回标题、时间（北京时间）、内容摘要。"""
    return route_to_vendor("get_cls_flash", count=count)


@tool
def get_cninfo_announcements(
    code: Annotated[str, "A股6位代码，如 600519"],
    page_size: Annotated[int, "每页条数，默认20"] = 20,
) -> str:
    """查询巨潮公告历史，包含公告标题、发布时间、PDF详情页链接。"""
    return route_to_vendor("get_cninfo_announcements", code=code, page_size=page_size)
