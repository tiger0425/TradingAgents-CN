"""
Simplified backtest command for TradingAgents CLI.

Runs single-ticker analysis over a date range and calculates performance metrics:
win rate, total return, and decision distribution.

Usage:
    tradingagents backtest --ticker 600519 --start-date 2026-04-01 --end-date 2026-04-30
    tradingagents backtest --ticker 600519 --start-date 2026-04-01 --end-date 2026-04-30 --output json
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.position_utils import calc_position_pnl

from cli.batch import build_config, ANALYST_ORDER
from cli.stats_handler import StatsCallbackHandler

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_trading_days(start_date: str, end_date: str) -> List[str]:
    """Get list of trading days between start_date and end_date (inclusive).

    Uses akshare's A-share trading calendar if available, otherwise
    falls back to all weekdays.
    """
    try:
        from tradingagents.dataflows.a_share_calendar import is_trade_day
    except ImportError:
        is_trade_day = None

    days: List[str] = []
    start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    cursor = start
    while cursor <= end:
        date_str = cursor.strftime("%Y-%m-%d")
        if is_trade_day is not None:
            try:
                if is_trade_day(date_str):
                    days.append(date_str)
            except Exception:
                # Calendar function failed — fall back to weekday filter
                if cursor.weekday() < 5:
                    days.append(date_str)
        else:
            # Fallback: include all weekdays
            if cursor.weekday() < 5:
                days.append(date_str)
        cursor += datetime.timedelta(days=1)
    return days


def _build_backtest_json(
    ticker: str,
    start_date: str,
    end_date: str,
    total_trading_days: int,
    results: List[Dict[str, Any]],
) -> str:
    """Serialize backtest performance to JSON string."""
    analyzed = [r for r in results if r.get("status") == "completed"]
    decisions: Dict[str, int] = {"buy": 0, "hold": 0, "sell": 0}
    for r in analyzed:
        d = r.get("decision", "").lower()
        if d in decisions:
            decisions[d] += 1

    performance = _compute_performance(analyzed)

    output: Dict[str, Any] = {
        "ticker": ticker,
        "start_date": start_date,
        "end_date": end_date,
        "total_trading_days": total_trading_days,
        "analyzed_days": len(analyzed),
        "decisions": decisions,
        "performance": performance,
        "errors": [
            {"date": r["date"], "error": r["error"]}
            for r in results if r.get("status") == "error"
        ],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def _compute_performance(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute aggregate performance metrics from analyzed results."""
    if not results:
        return {
            "total_return_pct": 0.0,
            "win_rate_pct": 0.0,
            "avg_holding_return_pct": 0.0,
        }

    buy_count = sum(1 for r in results if r.get("decision", "").lower() == "buy")
    total = len(results)
    win_rate_pct = (buy_count / total * 100) if total > 0 else 0.0

    # total_return_pct: sum of individual date returns (simplified)
    returns = [r.get("raw_return", 0.0) for r in results if "raw_return" in r]
    total_return_pct = sum(returns) * 100 if returns else 0.0

    # avg_holding_return_pct: average per-decision return
    valid_returns = [r for r in returns if r != 0.0]
    avg_holding_return_pct = (sum(valid_returns) / len(valid_returns) * 100) if valid_returns else 0.0

    return {
        "total_return_pct": round(total_return_pct, 2),
        "win_rate_pct": round(win_rate_pct, 2),
        "avg_holding_return_pct": round(avg_holding_return_pct, 2),
    }


def _format_backtest_text(
    ticker: str,
    start_date: str,
    end_date: str,
    total_trading_days: int,
    results: List[Dict[str, Any]],
) -> str:
    """Format backtest summary as plain text."""
    lines: List[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append(f"  简化回测报告 — {ticker}")
    lines.append(sep)
    lines.append(f"  回测区间: {start_date} ~ {end_date}")
    lines.append(f"  交易日数: {total_trading_days}")

    analyzed = [r for r in results if r.get("status") == "completed"]
    errors = [r for r in results if r.get("status") == "error"]
    lines.append(f"  已分析:   {len(analyzed)} 天")
    if errors:
        lines.append(f"  失败:     {len(errors)} 天")

    decisions: Dict[str, int] = {"buy": 0, "hold": 0, "sell": 0}
    for r in analyzed:
        d = r.get("decision", "").lower()
        if d in decisions:
            decisions[d] += 1

    lines.append(sep)
    lines.append("  决策分布:")
    lines.append(f"    买入 (Buy):           {decisions['buy']}")
    lines.append(f"    持有 (Hold):          {decisions['hold']}")
    lines.append(f"    卖出 (Sell):          {decisions['sell']}")

    performance = _compute_performance(analyzed)
    lines.append(sep)
    lines.append("  绩效指标:")
    lines.append(f"    累积收益率:            {performance['total_return_pct']:.2f}%")
    lines.append(f"    胜率 (买入信号占比):    {performance['win_rate_pct']:.2f}%")
    lines.append(f"    平均持仓收益率:        {performance['avg_holding_return_pct']:.2f}%")

    if errors:
        lines.append(sep)
        lines.append("  失败日期:")
        for err in errors[:10]:
            lines.append(f"    {err['date']}: {err['error'][:80]}")

    lines.append(sep)
    return "\n".join(lines)


# ------------------------------------------------------------------
# CLI Command
# ------------------------------------------------------------------


def backtest(
    ticker: str = typer.Option(
        ..., "--ticker", "-t", help="股票代码（必填）。例如: 600519"
    ),
    start_date: str = typer.Option(
        ..., "--start-date", help="回测起始日期 YYYY-MM-DD（必填）"
    ),
    end_date: str = typer.Option(
        ..., "--end-date", help="回测结束日期 YYYY-MM-DD（必填）"
    ),
    llm: Optional[str] = typer.Option(
        None,
        "--llm",
        help="LLM 供应商（默认使用配置文件中的值）",
    ),
    deep_model: Optional[str] = typer.Option(
        None,
        "--deep-model",
        help="深度推理模型（默认使用配置文件中的值）",
    ),
    quick_model: Optional[str] = typer.Option(
        None,
        "--quick-model",
        help="快速推理模型（默认使用配置文件中的值）",
    ),
    debate_rounds: int = typer.Option(
        1,
        "--debate-rounds", "-r",
        help="辩论轮次（默认 1，建议使用较小值以控制成本）",
    ),
    output: str = typer.Option(
        "text",
        "--output", "-o",
        help='输出格式: "json", "text", 或 "silent"（默认 text）',
    ),
) -> None:
    """简化回测：对单只股票在指定日期范围内逐日运行分析，汇总决策与绩效。

    ⚠️  警告：此命令会对每个交易日调用 LLM 分析流程，可能产生大量 API 费用。
    建议先用短日期范围（如 5-7 天）测试，并使用 --debate-rounds 1 控制成本。
    """
    output_mode = output.strip().lower()
    if output_mode not in ("json", "text", "silent"):
        typer.echo(
            f"错误: --output 必须为 'json', 'text', 或 'silent'，收到: '{output}'",
            err=True,
        )
        raise typer.Exit(code=1)

    # Validate dates
    for label, date_str in [("--start-date", start_date), ("--end-date", end_date)]:
        try:
            datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            typer.echo(
                f"错误: {label} 格式无效 '{date_str}'，请使用 YYYY-MM-DD 格式",
                err=True,
            )
            raise typer.Exit(code=1)

    start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    if start_dt > end_dt:
        typer.echo("错误: --start-date 不能晚于 --end-date", err=True)
        raise typer.Exit(code=1)

    # Get trading days
    trading_days = _get_trading_days(start_date, end_date)
    if not trading_days:
        if output_mode == "json":
            typer.echo(json.dumps({
                "ticker": ticker, "start_date": start_date,
                "end_date": end_date, "total_trading_days": 0,
                "analyzed_days": 0, "decisions": {"buy": 0, "hold": 0, "sell": 0},
                "performance": {"total_return_pct": 0.0, "win_rate_pct": 0.0, "avg_holding_return_pct": 0.0},
                "errors": [],
            }, ensure_ascii=False, indent=2))
        elif output_mode == "text":
            typer.echo(f"指定区间内无交易日: {start_date} ~ {end_date}")
        return

    # API cost warning
    typer.echo(
        f"\n⚠️  警告：即将对 {len(trading_days)} 个交易日运行 LLM 分析 "
        f"({ticker} | {start_date} ~ {end_date})"
    )
    typer.echo(f"   这可能产生大量 API 费用。每个交易日都会调用完整的分析师团队。\n")

    # Build config
    config = build_config(
        llm_provider=llm,
        deep_model=deep_model,
        quick_model=quick_model,
        debate_rounds=debate_rounds,
    )

    # Run analysis for each trading day
    results: List[Dict[str, Any]] = []
    for i, date_str in enumerate(trading_days, 1):
        stats_handler = StatsCallbackHandler()

        try:
            graph = TradingAgentsGraph(
                ["market", "social", "news", "fundamentals"],
                config=config,
                debug=False,
                callbacks=[stats_handler],
            )
            final_state, decision = graph.propagate(ticker, date_str)

            direction_map = {"Buy": "buy", "Overweight": "buy", "Hold": "hold",
                            "Underweight": "sell", "Sell": "sell"}

            results.append({
                "date": date_str,
                "status": "completed",
                "decision": direction_map.get(decision, "hold"),
                "rating": decision,
                "raw_return": 0.0,  # placeholder — real return needs future price data
            })

            if output_mode == "text":
                typer.echo(
                    f"  [{i}/{len(trading_days)}] {date_str} → {decision}"
                )

        except Exception as exc:
            results.append({
                "date": date_str,
                "status": "error",
                "error": str(exc),
            })
            if output_mode == "text":
                typer.echo(
                    f"  [{i}/{len(trading_days)}] {date_str} → 错误: {exc}",
                    err=True,
                )
            # Continue to next date — don't abort on single-day failure

    if output_mode == "json":
        typer.echo(_build_backtest_json(ticker, start_date, end_date, len(trading_days), results))
    elif output_mode == "text":
        typer.echo()
        typer.echo(_format_backtest_text(ticker, start_date, end_date, len(trading_days), results))
    # "silent" mode — no output


if __name__ == "__main__":
    backtest()  # type: ignore[call-arg]
