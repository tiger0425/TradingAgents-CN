"""Tomorrow's trading plan generator.

Produces actionable entry/target/stop-loss recommendations for each
position based on market data, volatility, and A-share constraints.

The plan is data-driven (not LLM-based) so it's fast, deterministic,
and always available — even without API keys.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import akshare as ak
except ImportError:
    ak = None


def _get_history(symbol: str, days: int = 30):
    """Get recent daily OHLCV for support/resistance/ATR calculation."""
    if ak is None or pd is None:
        return None
    try:
        end = datetime.now()
        start = end - timedelta(days=days * 2)
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is not None and not df.empty:
            df = df.sort_values("日期")
            return df
        return None
    except Exception:
        return None


def _calc_support_resistance(df) -> tuple:
    """Simple support/resistance from recent price range."""
    closes = df["收盘"].values
    highs = df["最高"].values
    lows = df["最低"].values

    if len(closes) < 5:
        return 0, 0

    # Resistance = recent high, Support = recent low
    resistance = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    support = min(lows[-20:]) if len(lows) >= 20 else min(lows)

    return support, resistance


def _calc_atr(df, period: int = 14) -> float:
    """Approximate ATR (Average True Range) as a volatility measure."""
    if len(df) < period + 1:
        return 0.0

    highs = df["最高"].values
    lows = df["最低"].values
    closes = df["收盘"].values

    trs = []
    for i in range(1, len(df)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        trs.append(max(hl, hc, lc))

    if len(trs) < period:
        return 0.0

    return sum(trs[-period:]) / period


def _calc_position_sizing(
    total_portfolio_value: float,
    risk_per_trade_pct: float = 2.0,
    num_positions: int = 3,
) -> float:
    """Calculate recommended position size per trade."""
    if total_portfolio_value <= 0:
        return 0
    max_risk = total_portfolio_value * risk_per_trade_pct / 100
    # Assume stop-loss at 5% → position = max_risk / 0.05
    return max_risk / 0.05


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

ActionType = str  # "买入" | "加仓" | "持有" | "减仓" | "卖出"


def generate_trading_plan(
    positions: List[Dict[str, Any]],
    total_portfolio_value: float = 0,
    risk_per_trade: float = 2.0,
) -> Dict[str, Any]:
    """Generate tomorrow's trading plan for all positions.

    For each position, calculates:
    - Action (add/hold/reduce based on P&L and volatility)
    - Suggested entry price (for adding)
    - Target price (take-profit level)
    - Stop-loss price
    - Position size recommendation

    Args:
        positions: List of dicts with symbol, quantity, cost_price, current_price
        total_portfolio_value: Total portfolio value for position sizing
        risk_per_trade: Max risk % per trade (default 2%)

    Returns:
        Dict with per-position plan and summary
    """
    if total_portfolio_value == 0:
        total_portfolio_value = sum(
            p.get("quantity", 0) * (p.get("current_price", 0) or p.get("cost_price", 0))
            for p in positions
        )

    plans = []
    for p in positions:
        symbol = p.get("symbol", "")
        qty = p.get("quantity", 0)
        cost = p.get("cost_price", 0)
        price = p.get("current_price", 0) or cost
        value = qty * price
        pnl_pct = (price - cost) / cost * 100 if cost > 0 else 0
        weight = (value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0

        hist = _get_history(symbol)
        if hist is not None and len(hist) > 5:
            support, resistance = _calc_support_resistance(hist)
            atr = _calc_atr(hist)
        else:
            support = price * 0.95
            resistance = price * 1.05
            atr = price * 0.02

        # Stop-loss: price - 2 * ATR (or -5% if no ATR)
        stop_loss = round(price - max(atr * 2, price * 0.03), 2)

        # Target: price + 3 * ATR (or +8% if no ATR)
        target = round(price + max(atr * 3, price * 0.06), 2)

        # Entry (for adding): near support level
        entry = round(support if support > 0 else price * 0.97, 2)

        # Validate against A-share limit constraints
        try:
            from tradingagents.dataflows.a_share_constraints import get_limit_prices
            limit_up, limit_down = get_limit_prices(symbol, price)
            # Clamp stop/target within limit bounds
            stop_loss = max(stop_loss, limit_down)
            target = min(target, limit_up)
            entry = max(min(entry, limit_up), limit_down)
        except Exception:
            pass

        # Action decision based on P&L and risk/reward
        rr_ratio = (target - price) / (price - stop_loss) if price - stop_loss > 0 else 0

        if pnl_pct < -8:
            action = "减仓"
            action_reason = f"亏损 {pnl_pct:.1f}%，建议减少仓位控制风险"
        elif pnl_pct > 15:
            action = "减仓"
            action_reason = f"盈利 {pnl_pct:.1f}%，建议部分止盈"
        elif weight > 30:
            action = "持有"
            action_reason = f"仓位占比 {weight:.1f}% 已较高，暂不加仓"
        elif rr_ratio > 2:
            action = "加仓"
            action_reason = f"风险回报比 {rr_ratio:.1f}，建议在 {entry} 附近加仓"
        else:
            action = "持有"
            action_reason = f"风险回报比 {rr_ratio:.1f}，当前价格观望"

        plans.append({
            "symbol": symbol,
            "name": p.get("name", symbol),
            "current_price": price,
            "cost_price": cost,
            "quantity": qty,
            "pnl_pct": round(pnl_pct, 1),
            "weight": round(weight, 1),
            "action": action,
            "reason": action_reason,
            "suggested_entry": entry,
            "target_price": target,
            "stop_loss": stop_loss,
            "rr_ratio": round(rr_ratio, 1),
            "atr": round(atr, 2),
            "support": round(support, 2) if support else None,
            "resistance": round(resistance, 2) if resistance else None,
        })

    # Summary
    add = [p for p in plans if p["action"] == "加仓"]
    hold = [p for p in plans if p["action"] == "持有"]
    reduce = [p for p in plans if p["action"] == "减仓"]

    return {
        "per_position": plans,
        "summary": {
            "add_count": len(add),
            "hold_count": len(hold),
            "reduce_count": len(reduce),
            "add_symbols": [p["symbol"] for p in add],
            "hold_symbols": [p["symbol"] for p in hold],
            "reduce_symbols": [p["symbol"] for p in reduce],
        },
    }


def format_plan_markdown(plan: Dict[str, Any]) -> str:
    """Format trading plan as Markdown for display/push."""
    lines = [
        "## 📋 明日操作计划",
        "",
    ]

    for p in plan.get("per_position", []):
        action = p["action"]
        emoji = {"买入": "🟢", "加仓": "🟢", "持有": "🟡", "减仓": "🔴", "卖出": "🔴"}.get(action, "⚪")
        lines.append(f"### {emoji} {p['symbol']} — [{action}]")
        lines.append(f"现价: {p['current_price']}  |  成本: {p['cost_price']}  |  盈亏: {p['pnl_pct']:+.1f}%")
        lines.append(f"风险回报比: {p['rr_ratio']}  |  仓位占比: {p['weight']}%")
        lines.append("")
        lines.append(f"| 指标 | 价格 |")
        lines.append(f"|------|-----|")
        lines.append(f"| **建议买入** | {p['suggested_entry']} |")
        lines.append(f"| **目标价** | {p['target_price']} |")
        lines.append(f"| **止损价** | {p['stop_loss']} |")
        lines.append(f"| **支撑位** | {p.get('support', '——')} |")
        lines.append(f"| **阻力位** | {p.get('resistance', '——')} |")
        lines.append("")
        lines.append(f"{p['reason']}")
        lines.append("")

    summary = plan.get("summary", {})
    lines.append(f"---")
    lines.append(f"操作建议: 加仓 {summary.get('add_count', 0)}  |  "
                 f"持有 {summary.get('hold_count', 0)}  |  "
                 f"减仓 {summary.get('reduce_count', 0)}")

    return "\n".join(lines)
