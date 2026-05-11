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
    """Fetch China market volatility (QVix) -- 50ETF/300ETF/500ETF.

    These are A-share "fear indices" based on ETF options implied volatility,
    more relevant than US VIX for Chinese market decisions.

    Levels (approximate, based on historical ranges):
      50QVix: >22 high vol, <15 low vol
      300QVix: >21 high vol, <16 low vol
      500QVix: >26 high vol, <20 low vol
    """
    results = []
    targets = [
        ("index_option_50etf_qvix",  "50QVix", 22, 15),
        ("index_option_300etf_qvix", "300QVix", 21, 16),
        ("index_option_500etf_qvix", "500QVix", 26, 20),
    ]
    for api_name, label, high_thresh, low_thresh in targets:
        try:
            fn = getattr(ak, api_name)
            df = fn()
            if df is None or df.empty:
                continue
            latest = _safe_float(df.iloc[-1]["close"])
            prev = _safe_float(df.iloc[-2]["close"]) if len(df) > 1 else latest
            chg = latest - prev

            if latest > high_thresh:
                level = "恐慌"
            elif latest > low_thresh:
                level = "谨慎"
            else:
                level = "平稳"

            results.append(f"{label} {latest:.2f} ({chg:+.2f}), {level}")
        except Exception:
            continue

    return "  ".join(results) if results else "QVix: 数据暂不可用"

def _fetch_northbound_flow() -> str:
    """Fetch northbound capital flow.

    Primary source: stock_hsgt_fund_flow_summary_em (East Money summary).
    - During trading hours (status=1): data is real-time and accurate.
    - Outside trading hours (status=3): all fields are zero/unreliable.

    Fallback: stock_hsgt_hist_em historical API.
    - East Money stopped publishing detailed flow data after 2024-08-16.
    - The historical fallback shows the last known valid data point.

    Manual override: set env var TRADINGAGENTS_NORTHBOUND_FLOW to a string
    like "净流入 +12.5亿" to override the automatic fetch.
    """
    import os
    manual = os.environ.get("TRADINGAGENTS_NORTHBOUND_FLOW", "").strip()
    if manual:
        return f"北向资金 {manual}（手动）"

    try:
        _ensure_akshare()
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            return "——"

        if "资金方向" not in df.columns:
            return "——"

        nb = df[df["资金方向"] == "北向"]
        if nb.empty:
            return "——"

        active = nb[nb["交易状态"] == 1]
        if not active.empty:
            total = 0.0
            for _, row in active.iterrows():
                net = _safe_float(row.get("资金净流入", 0))
                if net == 0:
                    net = _safe_float(row.get("成交净买额", 0))
                total += net
            if total != 0:
                direction = "净流入" if total > 0 else "净流出"
                return f"北向资金 {direction} {abs(total/1e8):.1f}亿"
            return "北向资金: 暂无数据（耐心等待盘中更新）"

        # Non-trading hours: try historical fallback
        try:
            hist = ak.stock_hsgt_hist_em(symbol="北向资金")
            if hist is not None and not hist.empty and "当日成交净买额" in hist.columns:
                valid_hist = hist[hist["当日成交净买额"].notna()]
                if not valid_hist.empty:
                    latest = valid_hist.iloc[-1]
                    net = _safe_float(latest.get("当日成交净买额", 0))
                    if net != 0:
                        direction = "净流入" if net > 0 else "净流出"
                        return f"北向资金 {direction} {abs(net):.1f}亿（暂停更，最后数据{str(latest.get('日期',''))[:10]}）"
        except Exception:
            pass

        status_val = nb.iloc[0].get("交易状态", "?")
        return f"北向资金: 非交易时段（交易时间自动更新）"
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
