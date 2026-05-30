"""
Market context data-fetching module for TradingAgents.

Aggregates A-share market-level context (index status, sector rotation,
capital flows, market breadth) using akshare APIs.

This module contains ZERO LLM calls and ZERO langchain imports.
It is a pure data function that returns a formatted Markdown string.
"""

import pandas as pd
import requests

# Lazy import guard — akshare is large and may not be installed everywhere
try:
    import akshare as ak
except ImportError:
    ak = None


def _ensure_akshare():
    """Raise a user-friendly error if akshare is not installed."""
    if ak is None:
        raise ImportError(
            "akshare is not installed. Please install it with: pip install akshare"
        )


def _ak_date(date_str: str) -> str:
    """Convert 'yyyy-mm-dd' to akshare's expected 'yyyymmdd' format."""
    return date_str.replace("-", "")


def _safe_float(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        if pd.isna(v):
            return default
        return v
    except (ValueError, TypeError, OverflowError):
        return default


def _fetch_index_status() -> str:
    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is None or df.empty:
            return "（数据暂不可用）"

        df = df.sort_values("date", ascending=False).reset_index(drop=True)
        latest = _safe_float(df.loc[0, "close"])
        prev = _safe_float(df.loc[1, "close"]) if len(df) > 1 else latest
        close_5d = _safe_float(df.loc[4, "close"]) if len(df) > 4 else prev

        daily_chg = (latest - prev) / prev * 100 if prev != 0 else 0.0
        chg_5d = (latest - close_5d) / close_5d * 100 if close_5d != 0 else 0.0

        return (
            f"上证指数: {latest:.2f} "
            f"(日涨跌 {daily_chg:+.2f}%, 5日涨跌 {chg_5d:+.2f}%)"
        )
    except Exception:
        return "（数据暂不可用）"


def _fetch_sector_rotation() -> str:
    try:
        from tradingagents.dataflows.a_stock_data import _get_session
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1,
            "pz": 100,
            "po": 1,
            "np": 1,
            "fltt": 2,
            "invt": 2,
            "fs": "m:90+t:2",
            "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
        }
        resp = _get_session().get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        diff = data.get("data", {}).get("diff", [])
        if not diff:
            return "（数据暂不可用）"

        sectors = []
        for item in diff:
            name = str(item.get("f14", ""))
            if not name:
                continue
            change_pct = _safe_float(item.get("f3", 0))
            sectors.append((name, change_pct))

        if not sectors:
            return "（数据暂不可用）"

        sectors.sort(key=lambda x: x[1], reverse=True)

        top3 = sectors[:3]
        bottom3 = sectors[-3:]

        top_str = "、".join(f"{name}({val:+.2f})" for name, val in top3)
        bottom_str = "、".join(f"{name}({val:+.2f})" for name, val in reversed(bottom3))

        return f"领涨: {top_str} | 领跌: {bottom_str}"
    except Exception:
        return "（数据暂不可用）"


def _fetch_capital_flow() -> str:
    try:
        df = ak.stock_market_fund_flow()
        if df is None or df.empty:
            return "（数据暂不可用）"

        row = df.iloc[-1]
        main_net = _safe_float(row.get("主力净流入-净额", 0)) / 1e8
        main_pct = _safe_float(row.get("主力净流入-净占比", 0))
        super_large = _safe_float(row.get("超大单净流入-净额", 0)) / 1e8
        large = _safe_float(row.get("大单净流入-净额", 0)) / 1e8

        return (
            f"主力净流入: {main_net:+.0f}亿元 "
            f"(占比 {main_pct:+.2f}%) | "
            f"超大单: {super_large:+.0f}亿元 | "
            f"大单: {large:+.0f}亿元"
        )
    except Exception:
        return "（数据暂不可用）"


def _fetch_market_breadth(trade_date: str) -> str:
    try:
        df = ak.stock_sse_deal_daily(date=_ak_date(trade_date))
        if df is None or df.empty:
            return "（数据暂不可用）"

        # This API returns rows labeled by 单日情况 and columns by board type.
        # Columns: 单日情况 | 股票 | 主板A | 主板B | 科创板 | 股票回购
        # Rows: 挂牌数, 市价总值, 流通市值, 成交金额, 成交量, 平均市盈率, 换手率, 流通换手率
        label_col = "单日情况"

        # Find the "挂牌数" row (total listed stocks)
        listed_mask = df[label_col] == "挂牌数"
        total_stocks = int(_safe_float(df.loc[listed_mask, "股票"].iloc[0])) if listed_mask.any() else 0

        # Find the "成交金额" row (total turnover, already in 亿元)
        vol_mask = df[label_col] == "成交金额"
        volume_yi = _safe_float(df.loc[vol_mask, "股票"].iloc[0]) if vol_mask.any() else 0.0

        return f"上证挂牌: {total_stocks}只 | 成交额: {volume_yi:.0f}亿元"
    except Exception:
        return "（数据暂不可用）"



def _try_prev_trade_day(date_str: str, max_back: int = 4) -> str:
    """Fall back to latest trading day when data is unavailable."""
    try:
        from tradingagents.dataflows.a_share_calendar import is_trade_day
        from datetime import datetime, timedelta
        d = datetime.strptime(date_str, "%Y-%m-%d")
        for i in range(max_back + 1):
            check = (d - timedelta(days=i)).strftime("%Y-%m-%d")
            try:
                if is_trade_day(check):
                    return check
            except Exception:
                pass
    except Exception:
        pass
    return date_str


def fetch_market_context(trade_date: str, market_type: str = "A_SHARE") -> str:
    """Fetch and format A-share market-level context data.

    Aggregates index status, sector rotation, capital flow, and market
    breadth data via akshare APIs.  Returns a Markdown string suitable
    for LLM prompt injection.

    Args:
        trade_date: Trading date in ``"yyyy-mm-dd"`` format.
        market_type: ``"A_SHARE"`` for Chinese market context,
                     any other value returns an unavailable message.

    Returns:
        Markdown-formatted string with up to four context sections.
        Total length is capped at 2000 characters.
    """
    if market_type != "A_SHARE":
        return "Market context unavailable for US stocks"

    _ensure_akshare()

    resolved_date = _try_prev_trade_day(trade_date)

    sections = [
        f"## 指数状态\n{_fetch_index_status()}",
        f"## 板块轮动\n{_fetch_sector_rotation()}",
        f"## 资金流向\n{_fetch_capital_flow()}",
        f"## 市场宽度\n{_fetch_market_breadth(resolved_date)}",
    ]

    result = "\n\n".join(sections)

    if len(result) > 2000:
        result = result[:1997] + "..."

    return result
