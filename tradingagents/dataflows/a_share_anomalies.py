"""A-share market anomaly detection engine.

Detects abnormal trading signals from akshare real-time market data:
- Limit-up / limit-down pools
- 炸板 (Zhaban: stocks that hit limit-up then broke)
- 天地板 (Tiandiban: extreme swing from limit-up to limit-down or vice versa)
- Consecutive limit moves (连板)
- Volume / price anomalies

Usage:
    from tradingagents.dataflows.a_share_anomalies import detect_anomalies
    result = detect_anomalies("2026-05-09")
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import akshare as ak
except ImportError:
    ak = None


def _ensure_akshare():
    if ak is None:
        raise ImportError("akshare is required. Install: pip install akshare")


def _fmt_date(date_str: str) -> str:
    """Convert yyyy-mm-dd to yyyymmdd."""
    return date_str.replace("-", "")


def get_limit_up_pool(date: str) -> List[Dict[str, Any]]:
    """Get today's limit-up stocks from East Money.

    Returns list of dicts with: code, name, price, change_pct,涨停统计,
    probably columns from ak.stock_zt_pool_em.
    """
    _ensure_akshare()
    try:
        df = ak.stock_zt_pool_em(date=_fmt_date(date))
        if df is None or df.empty:
            return []
        cols = list(df.columns)
        results = []
        for _, row in df.iterrows():
            entry = {
                "code": row.get("代码", row.get(cols[0], "")),
                "name": row.get("名称", row.get(cols[1], "")),
                "price": row.get("最新价", "N/A"),
                "change_pct": row.get("涨跌幅", "N/A"),
                "limit_count": row.get("涨停统计", row.get("连板数", 1)),
            }
            results.append(entry)
        return results
    except Exception as e:
        logger.warning("get_limit_up_pool failed: %s", e)
        return []


def get_limit_down_pool(date: str) -> List[Dict[str, Any]]:
    """Get today's limit-down stocks."""
    _ensure_akshare()
    try:
        df = ak.stock_zt_pool_dtgc_em(date=_fmt_date(date))
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            entry = {
                "code": row.get("代码", ""),
                "name": row.get("名称", ""),
                "price": row.get("最新价", "N/A"),
                "change_pct": row.get("涨跌幅", "N/A"),
            }
            results.append(entry)
        return results
    except Exception as e:
        logger.warning("get_limit_down_pool failed: %s", e)
        return []


def get_zhaban_pool(date: str) -> List[Dict[str, Any]]:
    """Get today's 炸板 (stocks that hit limit-up then broke)."""
    _ensure_akshare()
    try:
        df = ak.stock_zt_pool_zbgc_em(date=_fmt_date(date))
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            entry = {
                "code": row.get("代码", ""),
                "name": row.get("名称", ""),
                "price": row.get("最新价", "N/A"),
                "change_pct": row.get("涨跌幅", "N/A"),
                "zhaban_count": row.get("炸板次数", "N/A"),
            }
            results.append(entry)
        return results
    except Exception as e:
        logger.warning("get_zhaban_pool failed: %s", e)
        return []


def get_strong_pool(date: str) -> List[Dict[str, Any]]:
    """Get today's 强势股池."""
    _ensure_akshare()
    try:
        df = ak.stock_zt_pool_strong_em(date=_fmt_date(date))
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            entry = {
                "code": row.get("代码", ""),
                "name": row.get("名称", ""),
                "price": row.get("最新价", "N/A"),
                "change_pct": row.get("涨跌幅", "N/A"),
            }
            results.append(entry)
        return results
    except Exception as e:
        logger.warning("get_strong_pool failed: %s", e)
        return []


def get_previous_limit_up_pool(date: str) -> List[Dict[str, Any]]:
    """Get yesterday's limit-up stocks (to detect consecutive limits)."""
    _ensure_akshare()
    try:
        df = ak.stock_zt_pool_previous_em(date=_fmt_date(date))
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.iterrows():
            entry = {
                "code": row.get("代码", ""),
                "name": row.get("名称", ""),
                "price": row.get("最新价", "N/A"),
            }
            results.append(entry)
        return results
    except Exception as e:
        logger.warning("get_previous_limit_up_pool failed: %s", e)
        return []


# ============================================================================
# Detection functions
# ============================================================================


def detect_limit_moves(date: str) -> Dict[str, Any]:
    """Detect stocks hitting limit-up and limit-down today.

    Returns dict with:
        limit_up: List of limit-up stocks
        limit_down: List of limit-down stocks
        count_up: int
        count_down: int
    """
    up = get_limit_up_pool(date)
    down = get_limit_down_pool(date)
    return {
        "limit_up": up,
        "limit_down": down,
        "count_up": len(up),
        "count_down": len(down),
        "date": date,
    }


def detect_zhaban(date: str) -> List[Dict[str, Any]]:
    """Detect 炸板 stocks (opened limit-up)."""
    return get_zhaban_pool(date)


def detect_tiandiban(date: str) -> List[Dict[str, Any]]:
    """Detect 天地板 — stocks appearing in BOTH limit-up and limit-down pools.

    This is a heuristic: if a stock is in both pools on the same day,
    it likely experienced extreme intraday swings.
    """
    up_codes = {s["code"] for s in get_limit_up_pool(date)}
    down = get_limit_down_pool(date)
    results = []
    for s in down:
        if s["code"] in up_codes:
            results.append(s)
    return results


def detect_consecutive_limits(date: str, min_days: int = 3) -> List[Dict[str, Any]]:
    """Detect stocks with consecutive limit-up days.

    Uses today's limit-up pool to identify them (akshare's data often includes
    涨停统计/连板数 column directly).
    """
    up = get_limit_up_pool(date)
    results = []
    for s in up:
        lc = s.get("limit_count")
        if lc is not None:
            try:
                count = int(lc) if not isinstance(lc, int) else lc
                if count >= min_days:
                    results.append(s)
            except (ValueError, TypeError):
                pass
    return results


def detect_all_anomalies(date: str | None = None) -> Dict[str, Any]:
    """Run all anomaly detectors and return combined result.

    Args:
        date: Trading date string (yyyy-mm-dd). Defaults to today.

    Returns:
        Dict with keys: date, limit_moves, zhaban, tiandiban, consecutive_limits
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    return {
        "date": date,
        "limit_moves": detect_limit_moves(date),
        "zhaban": detect_zhaban(date),
        "tiandiban": detect_tiandiban(date),
        "consecutive_limits": detect_consecutive_limits(date, min_days=3),
    }
