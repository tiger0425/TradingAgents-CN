"""Macro / global market context data-fetching module.

Aggregates data that affects A-share decisions:
- US equities (Dow / SPX / Nasdaq)
- USD/CNY exchange rate
- Commodities (gold, crude oil, copper)
- VIX fear index
- Northbound capital flow (北向资金)
- China bond yield (10Y)

Pure data functions. ZERO LLM calls, ZERO langchain imports.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import akshare as ak
except ImportError:
    ak = None


def _ensure_akshare():
    if ak is None:
        raise ImportError("akshare is required. pip install akshare")


def _safe_float(val, default: float = 0.0) -> float:
    try:
        v = float(val)
        if pd.isna(v):
            return default
        return v
    except (ValueError, TypeError):
        return default


def _try_prev_trade_day(date_str: str, max_back: int = 3) -> Optional[str]:
    """Fall back up to max_back days to find a trading day."""
    from tradingagents.dataflows.a_share_calendar import is_trade_day
    d = datetime.strptime(date_str, "%Y-%m-%d")
    for i in range(max_back + 1):
        check = (d - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            if is_trade_day(check):
                return check
        except Exception:
            if i < 5:  # weekday fallback
                wd = (d - timedelta(days=i)).weekday()
                if wd < 5:
                    return check
    return date_str


# ---------------------------------------------------------------------------
# Individual data fetchers
# ---------------------------------------------------------------------------

def _fetch_us_indices() -> str:
    """Fetch US stock index status: Dow, SPX, Nasdaq change %."""
    try:
        _ensure_akshare()
        df = ak.index_us_stock_sina()
        if df is None or df.empty:
            return "——"

        # S&P 500, Nasdaq, Dow Jones
        targets = {"标普500": ".INX", "纳斯达克": ".IXIC", "道琼斯": ".DJI"}
        parts = []
        for name, code in targets.items():
            rows = df[df["代码"] == code]
            if rows.empty:
                continue
            r = rows.iloc[0]
            price = _safe_float(r.get("最新价", 0))
            chg_pct = _safe_float(r.get("涨跌幅", 0))
            parts.append(f"{name} {price:.0f} ({chg_pct:+.1f}%)")
        return "  ".join(parts) if parts else "——"
    except Exception as e:
        logger.debug("US indices failed: %s", e)
        return "——"


def _fetch_usd_cny() -> str:
    """Fetch USD/CNY exchange rate."""
    try:
        _ensure_akshare()
        df = ak.fx_spot_quote()
        if df is None or df.empty:
            return "——"
        rows = df[df["货币对"] == "美元/人民币"]
        if rows.empty:
            rows = df[df["货币对"].str.contains("美元/人民币", na=False)]
        if rows.empty:
            return "——"
        r = rows.iloc[0]
        price = _safe_float(r.get("最新价", 0))
        chg = _safe_float(r.get("涨跌额", 0))
        chg_pct = _safe_float(r.get("涨跌幅", 0))
        return f"USD/CNY {price:.4f} ({chg_pct:+.2f}%)"
    except Exception as e:
        logger.debug("USD/CNY failed: %s", e)
        return "——"


def _fetch_commodities() -> str:
    """Fetch key commodity prices: gold, crude oil, copper."""
    try:
        _ensure_akshare()
        df = ak.futures_foreign_commodity_realtime()
        if df is None or df.empty:
            return "——"

        targets = {
            "COMEX黄金": "黄金",
            "NYMEX原油": "原油",
            "COMEX铜": "铜",
        }
        parts = []
        for _, row in df.iterrows():
            name = str(row.get("名称", ""))
            for target_key, target_label in targets.items():
                if target_key in name:
                    price = _safe_float(row.get("最新价", 0))
                    chg_pct = _safe_float(row.get("涨跌幅", 0))
                    parts.append(f"{target_label} {price:.1f} ({chg_pct:+.1f}%)")
        return "  ".join(parts) if parts else "——"
    except Exception as e:
        logger.debug("Commodities failed: %s", e)
        return "——"


def _fetch_vix() -> str:
    """Fetch VIX fear index."""
    try:
        _ensure_akshare()
        df = ak.index_global_spot_em()
        if df is None or df.empty:
            return "——"
        rows = df[df["名称"].str.contains("VIX", na=False)]
        if rows.empty:
            return "——"
        r = rows.iloc[0]
        price = _safe_float(r.get("最新价", 0))
        chg_pct = _safe_float(r.get("涨跌幅", 0))
        vix_level = "恐慌" if price > 25 else ("谨慎" if price > 18 else "平稳")
        return f"VIX {price:.1f} ({chg_pct:+.1f}%), {vix_level}"
    except Exception as e:
        logger.debug("VIX failed: %s", e)
        return "——"


def _fetch_northbound_flow() -> str:
    """Fetch northbound capital flow summary."""
    try:
        _ensure_akshare()
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return "——"

        # Get the latest row
        latest = df.iloc[-1] if not df.empty else None
        if latest is None:
            return "——"

        net = _safe_float(latest.get("北向资金-净流入", latest.get("当日资金净流入", 0)))
        if net == 0:
            net = _safe_float(latest.get(list(latest.index[0] if hasattr(latest, 'index') and len(latest.index) > 0 else "当日资金净流入"), 0))

        buy = _safe_float(latest.get("北向资金-买入成交额", latest.get("买入成交额", 0)))
        sell = _safe_float(latest.get("北向资金-卖出成交额", latest.get("卖出成交额", 0)))

        if net != 0:
            direction = "净流入" if net > 0 else "净流出"
            return f"北向资金 {direction} {abs(net/1e8):.1f}亿"
        if buy != 0 and sell != 0:
            net = buy - sell
            direction = "净流入" if net > 0 else "净流出"
            return f"北向资金 {direction} {abs(net/1e8):.1f}亿"
        return "——"
    except Exception as e:
        logger.debug("Northbound flow failed: %s", e)
        return "——"


def _fetch_bond_yield() -> str:
    """Fetch China 10Y government bond yield."""
    try:
        _ensure_akshare()
        df = ak.bond_china_yield()
        if df is None or df.empty:
            return "——"
        # Find 10Y row
        for _, row in df.iterrows():
            if "10年" in str(row.get("期限", row.get("名称", ""))):
                y = _safe_float(row.get("收益率", row.get("收益", row.get("最新价", 0))))
                chg = _safe_float(row.get("涨跌BP", 0))
                return f"中国10Y国债 {y:.2f}% (BP {chg:+.1f})"
        return "——"
    except Exception as e:
        logger.debug("Bond yield failed: %s", e)
        return "——"


# ---------------------------------------------------------------------------
# Main aggregator
# ---------------------------------------------------------------------------

def fetch_macro_context(trade_date: str | None = None) -> str:
    """Fetch and format macro/global market context.

    Returns Markdown string suitable for LLM prompt injection.
    Cable is capped at 1200 characters.

    Args:
        trade_date: Almost unused (MOST macros use realtime / latest APIs).
            Kept for signature compatibility with fetch_market_context.
    """
    _ensure_akshare()

    sections = [
        "## 宏观/外围",
        f"美股: {_fetch_us_indices()}",
        f"汇率: {_fetch_usd_cny()}",
        f"大宗: {_fetch_commodities()}",
        f"VIX:  {_fetch_vix()}",
        f"北向: {_fetch_northbound_flow()}",
        f"国债: {_fetch_bond_yield()}",
    ]

    result = "\n".join(sections)
    if len(result) > 1200:
        result = result[:1197] + "..."

    return result
