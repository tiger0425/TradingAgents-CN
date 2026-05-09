"""
Portfolio overview command for TradingAgents CLI.

Reads all positions from PositionStateManager and displays a portfolio summary
with current market prices, per-position P&L, and concentration metrics.

Usage:
    tradingagents portfolio
    tradingagents portfolio --output json
    tradingagents portfolio --date 2026-05-09 --output json
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.agents.utils.position_state import PositionStateManager
from tradingagents.dataflows.position_utils import calc_position_pnl
from tradingagents.default_config import DEFAULT_CONFIG

# Lazy akshare import — not required at import-time
try:
    import akshare as ak

    _AKSHARE_AVAILABLE = True
except ImportError:
    ak = None  # type: ignore[assignment]
    _AKSHARE_AVAILABLE = False


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _fetch_spot_prices() -> Dict[str, Dict[str, Any]]:
    """Fetch current spot prices for all A-share stocks via akshare.

    Returns a dict keyed by 6-digit ticker code, each value is a dict
    with keys: name, current_price, change, change_pct.

    Returns empty dict if akshare not available or fetch fails.
    """
    if not _AKSHARE_AVAILABLE:
        return {}

    try:
        df = ak.stock_zh_a_spot()
    except Exception:
        return {}

    if df is None or df.empty:
        return {}

    prices: Dict[str, Dict[str, Any]] = {}
    from tradingagents.dataflows.akshare import _to_sina_symbol

    for _, row in df.iterrows():
        code = str(row.get("代码", ""))
        # Sina codes look like "sh600519" — strip prefix to 6-digit
        ticker = code[2:] if len(code) >= 3 and code[:2] in ("sh", "sz", "bj") else code
        if len(ticker) != 6 or not ticker.isdigit():
            continue
        try:
            prices[ticker] = {
                "name": str(row.get("名称", ticker)),
                "current_price": float(row.get("最新价", 0)),
                "change": float(row.get("涨跌额", 0)),
                "change_pct": float(row.get("涨跌幅", 0)),
            }
        except (ValueError, TypeError):
            continue

    return prices


def _build_portfolio_json(
    holdings: List[Dict[str, Any]],
    totals: Dict[str, Any],
    concentration: Dict[str, Any],
    date: str,
) -> str:
    """Serialize portfolio summary to JSON string."""
    output: Dict[str, Any] = {
        "date": date,
        "total_holdings": len(holdings),
        "total_cost": round(totals["total_cost"], 2),
        "total_market_value": round(totals["total_market_value"], 2),
        "total_pnl": round(totals["total_pnl"], 2),
        "total_pnl_pct": round(totals["total_pnl_pct"], 2),
        "holdings": [
            {
                "ticker": h["ticker"],
                "name": h.get("name", h["ticker"]),
                "cost_price": h["cost_price"],
                "quantity": h["quantity"],
                "current_price": h.get("current_price", 0),
                "market_value": round(h["market_value"], 2),
                "pnl_amount": round(h["pnl_amount"], 2),
                "pnl_pct": round(h["pnl_pct"], 2) if h["pnl_pct"] is not None else None,
                "weight": round(h["weight"], 2),
            }
            for h in holdings
        ],
        "concentration": {
            "top1_weight": round(concentration["top1_weight"], 2),
            "top3_weight": round(concentration["top3_weight"], 2),
            "num_holdings": concentration["num_holdings"],
        },
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def _format_portfolio_text(
    holdings: List[Dict[str, Any]],
    totals: Dict[str, Any],
    concentration: Dict[str, Any],
    date: str,
) -> str:
    """Format portfolio summary as plain text table."""
    lines: List[str] = []
    sep = "=" * 75

    lines.append(sep)
    lines.append(f"  持仓组合概览 — {date}")
    lines.append(sep)

    if not holdings:
        lines.append("\n  (无持仓记录)")
        return "\n".join(lines)

    # Header
    lines.append(
        f"  {'代码':<8} {'名称':<10} {'成本':>8} {'现价':>8} "
        f"{'持仓':>6} {'市值':>12} {'盈亏':>10} {'盈亏%':>8} {'权重':>7}"
    )
    lines.append("  " + "-" * 72)

    # Rows
    for h in holdings:
        name = h.get("name", "")[:8] if h.get("name") else h["ticker"]
        pnl_pct_str = f"{h['pnl_pct']:.2f}%" if h["pnl_pct"] is not None else "N/A"
        lines.append(
            f"  {h['ticker']:<8} {name:<10} "
            f"{h['cost_price']:>8.2f} {h.get('current_price', 0):>8.2f} "
            f"{h['quantity']:>6} {h['market_value']:>12.2f} "
            f"{h['pnl_amount']:>+10.2f} {pnl_pct_str:>8} "
            f"{h['weight']:>6.2f}%"
        )

    lines.append("  " + "-" * 72)
    lines.append(
        f"  {'合计':<8} {'':<10} {'':>8} {'':>8} "
        f"{'':>6} {totals['total_market_value']:>12.2f} "
        f"{totals['total_pnl']:>+10.2f} "
        f"{totals['total_pnl_pct']:>7.2f}% {'':>7}"
    )
    lines.append(sep)
    lines.append(f"  持仓数: {concentration['num_holdings']}")
    lines.append(f"  最大仓位占比: {concentration['top1_weight']:.2f}%")
    lines.append(f"  前三大仓位占比: {concentration['top3_weight']:.2f}%")
    lines.append(sep)

    return "\n".join(lines)


# ------------------------------------------------------------------
# CLI Command
# ------------------------------------------------------------------


def portfolio(
    date: str = typer.Option(
        datetime.datetime.now().strftime("%Y-%m-%d"),
        "--date", "-d",
        help="参考日期 YYYY-MM-DD（默认今天）",
    ),
    output: str = typer.Option(
        "text",
        "--output", "-o",
        help='输出格式: "json", "text", 或 "silent"（默认 text）',
    ),
) -> None:
    """查看当前持仓组合概览，包含各持仓浮动盈亏与集中度分析。

    从持久化持仓文件中读取所有仓位，通过实时行情计算最新市场价值与浮动盈亏。
    """
    output_mode = output.strip().lower()
    if output_mode not in ("json", "text", "silent"):
        typer.echo(
            f"错误: --output 必须为 'json', 'text', 或 'silent'，收到: '{output}'",
            err=True,
        )
        raise typer.Exit(code=1)

    # Validate date format
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        typer.echo(
            f"错误: 日期格式无效 '{date}'，请使用 YYYY-MM-DD 格式",
            err=True,
        )
        raise typer.Exit(code=1)

    # Read all positions
    psm = PositionStateManager(DEFAULT_CONFIG.copy())
    positions = psm.get_all()

    if not positions:
        if output_mode == "json":
            typer.echo(json.dumps({
                "date": date,
                "total_holdings": 0,
                "total_cost": 0.0,
                "total_market_value": 0.0,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "holdings": [],
                "concentration": {
                    "top1_weight": 0.0,
                    "top3_weight": 0.0,
                    "num_holdings": 0,
                },
            }, ensure_ascii=False, indent=2))
        elif output_mode == "text":
            typer.echo(_format_portfolio_text([], {}, {}, date))
        return

    # Fetch current prices
    spot_prices = _fetch_spot_prices()

    # Build holdings list
    holdings: List[Dict[str, Any]] = []
    total_cost = 0.0
    total_market_value = 0.0

    for ticker, pos in positions.items():
        cost_price = float(pos.get("cost_price", 0.0))
        quantity = int(pos.get("quantity", 0))
        total_cost += cost_price * quantity

        spot = spot_prices.get(ticker, {})
        current_price = spot.get("current_price", 0.0)
        name = spot.get("name", ticker)

        pnl = calc_position_pnl(current_price if current_price > 0 else cost_price, cost_price, quantity)
        market_value = current_price * quantity if current_price > 0 else cost_price * quantity

        total_market_value += market_value

        holdings.append({
            "ticker": ticker,
            "name": name,
            "cost_price": cost_price,
            "quantity": quantity,
            "current_price": current_price if current_price > 0 else cost_price,
            "market_value": market_value,
            "pnl_amount": pnl["pnl_amount"],
            "pnl_pct": pnl["pnl_pct"],
            "weight": 0.0,  # placeholder, computed below
        })

    # Compute weights and concentration
    for h in holdings:
        h["weight"] = (h["market_value"] / total_market_value * 100) if total_market_value > 0 else 0.0

    sorted_holdings = sorted(holdings, key=lambda h: h["weight"], reverse=True)

    total_pnl = sum(h["pnl_amount"] for h in holdings)
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    totals = {
        "total_cost": total_cost,
        "total_market_value": total_market_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
    }

    top1_weight = sorted_holdings[0]["weight"] if sorted_holdings else 0.0
    top3_weight = sum(h["weight"] for h in sorted_holdings[:3]) if sorted_holdings else 0.0
    concentration = {
        "top1_weight": top1_weight,
        "top3_weight": top3_weight,
        "num_holdings": len(sorted_holdings),
    }

    if output_mode == "json":
        typer.echo(_build_portfolio_json(sorted_holdings, totals, concentration, date))
    elif output_mode == "text":
        typer.echo(_format_portfolio_text(sorted_holdings, totals, concentration, date))
    # "silent" mode — no output


if __name__ == "__main__":
    portfolio()  # type: ignore[call-arg]
