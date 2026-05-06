"""
A-share trading calendar utilities.
Uses akshare's tool_trade_date_hist_sina() for accurate Chinese market calendar.

All functions accept/return date strings in "yyyy-mm-dd" format.
On error, fall back to simple weekday-based heuristic (weekdays = trading days).
"""
import functools
from datetime import datetime, timedelta

import pandas as pd


@functools.lru_cache(maxsize=1)
def _load_calendar() -> pd.DataFrame:
    """Load and cache the A-share trading calendar from Sina via akshare.

    Returns a DataFrame with at least a 'trade_date' column (datetime64).
    The result is cached to avoid repeated API calls within the same process.
    """
    import akshare as ak

    return ak.tool_trade_date_hist_sina()


def is_trade_day(date_str: str) -> bool:
    """判断指定日期是否为 A 股交易日。

    Args:
        date_str: 日期字符串，格式 "yyyy-mm-dd"。

    Returns:
        如果该日期是交易日返回 True，否则返回 False。
        异常时回退到周末判断（周一到周五视为交易日）。
    """
    try:
        calendar = _load_calendar()
        target = pd.Timestamp(date_str)
        return target in calendar["trade_date"].values
    except Exception:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.weekday() < 5


def next_trade_day(date_str: str) -> str:
    """获取指定日期之后的下一个交易日。

    Args:
        date_str: 起始日期字符串，格式 "yyyy-mm-dd"。

    Returns:
       下一个交易日字符串，格式 "yyyy-mm-dd"。
       如果 calendar 中找不到后续日期（例如数据截止日之后），返回 date_str 本身。
       异常时回退到逐日递增直到找到工作日。
    """
    try:
        calendar = _load_calendar()
        target = pd.Timestamp(date_str)
        future = calendar[calendar["trade_date"] > target]
        if future.empty:
            return date_str
        return future["trade_date"].iloc[0].strftime("%Y-%m-%d")
    except Exception:
        dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=1)
        return dt.strftime("%Y-%m-%d")


def prev_trade_day(date_str: str) -> str:
    """获取指定日期之前的上一个交易日。

    Args:
        date_str: 起始日期字符串，格式 "yyyy-mm-dd"。

    Returns:
        上一个交易日字符串，格式 "yyyy-mm-dd"。
        如果 calendar 中找不到更早的日期，返回 date_str 本身。
        异常时回退到逐日递减直到找到工作日。
    """
    try:
        calendar = _load_calendar()
        target = pd.Timestamp(date_str)
        past = calendar[calendar["trade_date"] < target]
        if past.empty:
            return date_str
        return past["trade_date"].iloc[-1].strftime("%Y-%m-%d")
    except Exception:
        dt = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        return dt.strftime("%Y-%m-%d")
