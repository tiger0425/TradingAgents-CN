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
    """Fetch US stock index status via Sina historical data."""
    targets = {"S&P500": ".INX", "Nasdaq": ".IXIC", "Dow": ".DJI"}
    parts = []
    for label, code in targets.items():
        try:
            df = ak.index_us_stock_sina(symbol=code)
            if df is None or len(df) < 2:
                continue
            latest = _safe_float(df.iloc[-1]["close"])
            prev = _safe_float(df.iloc[-2]["close"])
            chg = (latest - prev) / prev * 100 if prev else 0
            parts.append(f"{label} {latest:.0f} ({chg:+.1f}%)")
        except Exception:
            continue
    return "  ".join(parts) if parts else "——"


def _fetch_usd_cny() -> str:
    """Fetch USD/CNY exchange rate."""
    try:
        _ensure_akshare()
        df = ak.fx_spot_quote()
        if df is None or df.empty:
            return "——"
        rows = df[df["货币对"] == "美元/人民币"]
        if rows.empty:
            rows = df[df["货币对"].str.contains("USD/CNY|美元/人民币", na=False, regex=True)]
        if rows.empty:
            return "——"
        r = rows.iloc[0]
        buy = _safe_float(r.get("买报价", r.get("买价", 0)))
        sell = _safe_float(r.get("卖报价", r.get("卖价", 0)))
        if buy > 0:
            return f"USD/CNY {buy:.4f}"
        if sell > 0:
            return f"USD/CNY {sell:.4f}"
        return "——"
    except Exception as e:
        logger.debug("USD/CNY failed: %s", e)
        return "——"


def _fetch_commodities() -> str:
    """Fetch key commodity prices: gold, crude oil, copper."""
    try:
        _ensure_akshare()
        df = ak.futures_global_spot_em()
        if df is None or df.empty:
            return "——"

        # Filter for continuous contract (当月连续) or base contract (no month suffix)
        targets = {
            "黄金": ["迷你黄金"],       # 迷你黄金 (base)
            "原油": ["迷你原油"],       # 迷你原油 (base)
            "铜":   ["综合铜03", "COMEX铜"],  # try both naming conventions
        }
        parts = []
        for _, row in df.iterrows():
            name = str(row.get("名称", ""))
            # Resolve: prefer base contracts, then current month continuous
            for target_label, aliases in targets.items():
                found = False
                for alias in aliases:
                    if name == alias or (name.startswith(alias) and                        ("当月" in name or "连续" in name or name == alias)):
                        price = _safe_float(row.get("最新价", 0))
                        chg_pct = _safe_float(row.get("涨跌幅", 0))
                        if price > 0:
                            parts.append(f"{target_label} {price:.1f} ({chg_pct:+.1f}%)")
                            found = True
                            break
                if found:
                    break
        return "  ".join(parts) if parts else "——"
    except Exception as e:
        logger.debug("Commodities failed: %s", e)
        return "——"


def _fetch_vix() -> str:
    """Fetch VIX fear index with retry. Falls back gracefully on rate-limit."""
    import time as _time
    for attempt in range(2):
        try:
            df = ak.index_global_spot_em()
            if df is None or df.empty:
                return "VIX: 数据暂不可用"
            rows = df[df["名称"].str.contains("VIX", na=False)]
            if rows.empty:
                return "VIX: 数据暂不可用"
            r = rows.iloc[0]
            price = _safe_float(r.get("最新价", 0))
            chg_pct = _safe_float(r.get("涨跌幅", 0))
            vix_level = "恐慌" if price > 25 else ("谨慎" if price > 18 else "平稳")
            return f"VIX {price:.1f} ({chg_pct:+.1f}%), {vix_level}"
        except Exception:
            if attempt < 1:
                _time.sleep(3)
    return "VIX: 数据源暂时受限"


def _fetch_northbound_flow() -> str:
    """Fetch northbound capital flow summary."""
    try:
        _ensure_akshare()
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return "——"

        # Filter northbound (北向) rows only
        if "资金方向" in df.columns:
            df = df[df["资金方向"] == "北向"]

        if df.empty:
            return "——"

        # Sum across all northbound rows (沪股通+深股通)
        net_col = next((c for c in df.columns if "净流入" in c or "净买" in c), None)
        if net_col:
            total = _safe_float(df[net_col].sum())
            direction = "净流入" if total > 0 else "净流出"
            return f"北向资金 {direction} {abs(total/1e8):.1f}亿"

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

        # Columns: 曲线名称, 日期, 3月, 6月, 1年, 3年, 5年, 7年, 10年, 30年
        if "10年" in df.columns and len(df) > 0:
            latest = df.iloc[-1]
            y = _safe_float(latest.get("10年", 0))
            prev = _safe_float(df.iloc[-2].get("10年", 0)) if len(df) > 1 else y
            chg_bp = (y - prev) * 100 if prev else 0
            return f"中国10Y国债 {y:.2f}% (BP {chg_bp:+.1f})"

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
