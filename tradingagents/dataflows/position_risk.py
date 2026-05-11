"""Position risk exposure assessment module.

Evaluates portfolio-level risk:
- Market drop impact (大盘下跌时各持仓损益估算)
- Concentration risk (行业/个股集中度)
- Drawdown assessment (各持仓回撤评估)
- Beta exposure
- VaR (Value at Risk) estimation
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import akshare as ak
except ImportError:
    ak = None

_TRADING_DAYS_20 = 20
_TRADING_DAYS_60 = 60


def _ensure_deps():
    if pd is None:
        raise ImportError("pandas is required")
    if ak is None:
        raise ImportError("akshare is required")


def _fmt_date(d: str) -> str:
    return d.replace("-", "")


def _get_benchmark_data(days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch CSI 300 (沪深300) historical data for benchmark comparison."""
    try:
        _ensure_deps()
        end = datetime.now()
        start = end - timedelta(days=days * 2)  # buffer for non-trading days
        df = ak.stock_zh_a_hist(
            symbol="000300",
            period="daily",
            start_date=_fmt_date(start.strftime("%Y-%m-%d")),
            end_date=_fmt_date(end.strftime("%Y-%m-%d")),
            adjust="qfq",
        )
        if df is not None and not df.empty:
            df = df.sort_values("日期")
            df["return"] = df["收盘"].pct_change()
            return df
        return None
    except Exception:
        return None


def _get_stock_history(symbol: str, days: int = 60) -> Optional[pd.DataFrame]:
    """Fetch historical OHLCV for a stock."""
    try:
        _ensure_deps()
        end = datetime.now()
        start = end - timedelta(days=days * 2)
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=_fmt_date(start.strftime("%Y-%m-%d")),
            end_date=_fmt_date(end.strftime("%Y-%m-%d")),
            adjust="qfq",
        )
        if df is not None and not df.empty:
            df = df.sort_values("日期")
            df["return"] = df["收盘"].pct_change()
            return df
        return None
    except Exception:
        return None


def _calc_beta(stock_returns: pd.Series, benchmark_returns: pd.Series) -> Optional[float]:
    """Calculate beta: covariance(stock, benchmark) / variance(benchmark)."""
    combined = pd.concat([stock_returns, benchmark_returns], axis=1).dropna()
    if len(combined) < 10:
        return None
    cov = combined.iloc[:, 0].cov(combined.iloc[:, 1])
    var = combined.iloc[:, 1].var()
    if var == 0:
        return None
    return round(cov / var, 2)


def assess_market_drop_impact(
    positions: List[Dict[str, Any]],
    benchmark_drop_pct: float = 3.0,
) -> Dict[str, Any]:
    """Estimate portfolio impact if benchmark drops by given percentage.

    Uses each position's beta to estimate individual impact.
    If beta not available, defaults to beta=1.0.

    Args:
        positions: List of position dicts with keys: symbol, quantity, cost_price, current_price
        benchmark_drop_pct: Hypothetical benchmark drop % (positive number, e.g. 3.0 = 3% drop)

    Returns:
        Dict with: total_impact, total_value, impact_pct, per_position details
    """
    positions = [p for p in positions if p.get("quantity", 0) > 0]
    if not positions:
        return {"total_impact": 0, "total_value": 0, "impact_pct": 0, "positions": []}

    total_value = sum(
        p.get("quantity", 0) * (p.get("current_price", 0) or p.get("cost_price", 0))
        for p in positions
    )
    if total_value == 0:
        return {"total_impact": 0, "total_value": 0, "impact_pct": 0, "positions": []}

    per_pos = []
    for p in positions:
        symbol = p.get("symbol", "")
        qty = p.get("quantity", 0)
        price = p.get("current_price", 0) or p.get("cost_price", 0)
        value = qty * price

        # Try to get beta from historical data
        beta = _calc_beta_from_symbol(symbol)
        if beta is None:
            beta = 1.0  # default assumption

        est_drop = benchmark_drop_pct * abs(beta)
        est_loss = round(value * est_drop / 100, 2)

        per_pos.append({
            "symbol": symbol,
            "value": value,
            "beta": beta,
            "est_drop_pct": round(est_drop, 2),
            "est_loss": est_loss,
        })

    total_impact = round(sum(p["est_loss"] for p in per_pos), 2)
    impact_pct = round(total_impact / total_value * 100, 2) if total_value else 0

    return {
        "benchmark_drop_pct": benchmark_drop_pct,
        "total_value": total_value,
        "total_impact": total_impact,
        "impact_pct": impact_pct,
        "positions": per_pos,
    }


def _calc_beta_from_symbol(symbol: str) -> Optional[float]:
    """Calculate beta for a stock against CSI 300."""
    bench = _get_benchmark_data(60)
    stock = _get_stock_history(symbol, 60)
    if bench is None or stock is None:
        return None
    return _calc_beta(stock["return"], bench["return"])


def assess_concentration_risk(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Assess portfolio concentration risk using Herfindahl-Hirschman Index (HHI).

    HHI = sum((weight_i)^2) where weight_i is each position's proportion.
    HHI > 0.2 = concentrated, HHI > 0.4 = very concentrated.

    Args:
        positions: List of position dicts with keys: symbol, quantity, current_price/cost_price

    Returns:
        Dict with: hhi, concentration_level, largest_position, largest_weight, positions
    """
    positions = [p for p in positions if p.get("quantity", 0) > 0]
    if not positions:
        return {"hhi": 0, "concentration_level": "none", "largest_position": "", "largest_weight": 0}

    total_value = sum(
        p.get("quantity", 0) * (p.get("current_price", 0) or p.get("cost_price", 0))
        for p in positions
    )
    if total_value == 0:
        return {"hhi": 0, "concentration_level": "none", "largest_position": "", "largest_weight": 0}

    weights = []
    for p in positions:
        v = p.get("quantity", 0) * (p.get("current_price", 0) or p.get("cost_price", 0))
        w = v / total_value
        weights.append({"symbol": p.get("symbol", ""), "value": v, "weight": round(w, 4)})

    hhi = sum(w["weight"] ** 2 for w in weights)
    largest = max(weights, key=lambda x: x["weight"])
    n_positions = len(positions)

    if hhi > 0.4:
        level = "非常集中"
    elif hhi > 0.2:
        level = "比较集中"
    elif hhi > 0.1:
        level = "适度集中"
    else:
        level = "分散"

    return {
        "hhi": round(hhi, 4),
        "concentration_level": level,
        "largest_position": largest["symbol"],
        "largest_weight": round(largest["weight"] * 100, 2),
        "num_positions": n_positions,
        "positions": weights,
    }


def assess_drawdown(positions: List[Dict[str, Any]], lookback_days: int = 20) -> Dict[str, Any]:
    """Assess drawdown risk for each position.

    For each position, calculates the maximum drawdown over the lookback period.
    Also computes portfolio-level drawdown.

    Args:
        positions: List of position dicts with keys: symbol, quantity, cost_price
        lookback_days: Lookback period in days

    Returns:
        Dict with per-position drawdown and portfolio-level summary
    """
    results = []
    max_portfolio_dd = 0.0

    for p in positions:
        symbol = p.get("symbol", "")
        if not symbol:
            continue
        stock_df = _get_stock_history(symbol, lookback_days)
        if stock_df is None or stock_df.empty or "收盘" not in stock_df.columns:
            continue

        prices = stock_df["收盘"].values
        if len(prices) < 2:
            continue

        peak = prices[0]
        max_dd = 0.0
        for price in prices:
            if price > peak:
                peak = price
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd

        results.append({
            "symbol": symbol,
            "max_drawdown_pct": round(max_dd * 100, 2),
            "lookback_days": lookback_days,
        })
        if max_dd > max_portfolio_dd:
            max_portfolio_dd = max_dd

    return {
        "max_portfolio_drawdown_pct": round(max_portfolio_dd * 100, 2),
        "per_position": results,
    }


def assess_all_risks(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run all risk assessments and return combined result.

    Args:
        positions: Position dicts with symbol, quantity, cost_price, current_price

    Returns:
        Combined risk assessment dict
    """
    return {
        "market_drop_risk": assess_market_drop_impact(positions, 3.0),
        "market_drop_5pct": assess_market_drop_impact(positions, 5.0),
        "concentration": assess_concentration_risk(positions),
        "drawdown": assess_drawdown(positions, 20),
    }


# ============================================================================
# Cross-position correlation & hedge analysis (Phase 2)
# ============================================================================

def assess_correlation_risk(positions, lookback_days=60):
    """Calculate Pearson correlation matrix between holdings.

    Detects holdings that move together (correlation > 0.7 = high risk of
    simultaneous drawdown).  Uses daily returns over *lookback_days*.

    Returns dict with:
        correlation_matrix: dict of stock-pair → correlation
        high_correlation_pairs: list of pairs with |corr| > 0.7
        avg_correlation: average absolute pairwise correlation
        risk_level: "低" / "中" / "高"
    """
    positions = [p for p in positions if p.get("quantity", 0) > 0]
    if len(positions) < 2:
        return {"correlation_matrix": {}, "high_correlation_pairs": [],
                "avg_correlation": 0, "risk_level": "none"}

    # Fetch historical returns for each symbol
    symbols = [p["symbol"] for p in positions]
    returns = {}
    for sym in symbols:
        df = _get_stock_history(sym, lookback_days)
        if df is not None and "return" in df.columns:
            ser = df["return"].dropna()
            if len(ser) > 10:
                returns[sym] = ser

    if len(returns) < 2:
        return {"correlation_matrix": {}, "high_correlation_pairs": [],
                "avg_correlation": 0, "risk_level": "low"}

    # Build correlation matrix
    corr_matrix = {}
    pairs = []
    syms = list(returns.keys())
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            s1, s2 = syms[i], syms[j]
            common = returns[s1].index.intersection(returns[s2].index)
            if len(common) < 10:
                continue
            r1 = returns[s1][common]
            r2 = returns[s2][common]
            corr = round(r1.corr(r2), 3)
            key = f"{s1}-{s2}"
            corr_matrix[key] = corr
            if abs(corr) > 0.7:
                pairs.append({"pair": key, "correlation": corr,
                              "symbols": [s1, s2]})

    avg_corr = round(sum(abs(v) for v in corr_matrix.values()) / max(len(corr_matrix), 1), 3)
    if avg_corr > 0.7:
        risk_level = "高"
    elif avg_corr > 0.4:
        risk_level = "中"
    else:
        risk_level = "低"

    return {
        "correlation_matrix": corr_matrix,
        "high_correlation_pairs": pairs,
        "avg_correlation": avg_corr,
        "risk_level": risk_level,
    }


def detect_hedge_opportunities(positions, lookback_days=60):
    """Detect natural hedging relationships between holdings.

    A "hedge" is defined as a pair with strong NEGATIVE correlation
    (correlation < -0.3), meaning one tends to rise when the other falls.

    Returns dict with:
        hedge_pairs: list of negatively correlated pairs
        summary: text description
    """
    corr_result = assess_correlation_risk(positions, lookback_days)
    matrix = corr_result.get("correlation_matrix", {})

    hedge_pairs = []
    for pair_key, corr in matrix.items():
        if corr < -0.3:
            s1, s2 = pair_key.split("-")
            hedge_pairs.append({
                "pair": pair_key,
                "correlation": corr,
                "symbols": [s1, s2],
                "strength": "强对冲" if corr < -0.5 else "弱对冲",
            })

    if hedge_pairs:
        summary = f"识别到 {len(hedge_pairs)} 组对冲关系：" + \
                  "；".join(f"{p['symbols'][0]} vs {p['symbols'][1]}({p['correlation']})"
                           for p in hedge_pairs)
    else:
        summary = "持仓间未发现显著对冲关系（无强负相关对）"

    return {"hedge_pairs": hedge_pairs, "summary": summary}
