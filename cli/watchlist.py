"""
Watchlist management commands for TradingAgents CLI.

Usage:
    tradingagents watchlist add 600519 --name "贵州茅台" --priority 1
    tradingagents watchlist remove 600519
    tradingagents watchlist list
    tradingagents watchlist get 600519
    tradingagents watchlist set-alert 600519 --price-above 1600
    tradingagents watchlist remove-alert 600519 --price-above
"""

from __future__ import annotations

import json
from typing import Optional

import typer

from tradingagents.watchlist import WatchlistManager

watchlist_app = typer.Typer(
    name="watchlist",
    help="管理自选股监视列表。",
    add_completion=False,
)


@watchlist_app.command()
def add(
    ticker: str = typer.Argument(..., help="股票代码。例如: 600519"),
    name: str = typer.Option("", "--name", "-n", help="股票名称。例如: 贵州茅台"),
    priority: int = typer.Option(5, "--priority", "-p", help="优先级（数值越低越重要）"),
    price_above: Optional[float] = typer.Option(None, "--price-above", help="价格上限告警"),
    price_below: Optional[float] = typer.Option(None, "--price-below", help="价格下限告警"),
    rsi_oversold: bool = typer.Option(False, "--rsi-oversold", help="RSI 超卖告警"),
    rsi_overbought: bool = typer.Option(False, "--rsi-overbought", help="RSI 超买告警"),
    volume_surge: Optional[float] = typer.Option(None, "--volume-surge", help="成交量激增倍数告警"),
) -> None:
    """添加股票到监视列表。如果已存在则更新信息。"""
    alerts = {}
    if price_above is not None:
        alerts["price_above"] = price_above
    if price_below is not None:
        alerts["price_below"] = price_below
    if rsi_oversold:
        alerts["rsi_oversold"] = True
    if rsi_overbought:
        alerts["rsi_overbought"] = True
    if volume_surge is not None:
        alerts["volume_surge"] = volume_surge

    mgr = WatchlistManager()
    entry = mgr.add(ticker, name=name, priority=priority, alerts=alerts)
    typer.echo(f"已添加: {entry['ticker']} {entry['name']} (优先级: {entry['priority']})")


@watchlist_app.command()
def remove(
    ticker: str = typer.Argument(..., help="股票代码。例如: 600519"),
) -> None:
    """从监视列表中移除股票。"""
    mgr = WatchlistManager()
    if mgr.remove(ticker):
        typer.echo(f"已移除: {ticker}")
    else:
        typer.echo(f"未找到: {ticker}", err=True)
        raise typer.Exit(code=1)


@watchlist_app.command()
def list(
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
) -> None:
    """列出监视列表中的所有股票（按优先级排序）。"""
    output_mode = output.strip().lower()
    if output_mode not in ("text", "json"):
        typer.echo(f"错误: --output 必须为 'text' 或 'json'，收到: '{output}'", err=True)
        raise typer.Exit(code=1)

    mgr = WatchlistManager()
    stocks = mgr.list()

    if output_mode == "json":
        typer.echo(json.dumps(stocks, ensure_ascii=False, indent=2))
        return

    if not stocks:
        typer.echo("监视列表为空。")
        return

    # Text table
    header = f"{'代码':<10} {'名称':<16} {'优先级':<8} {'告警数':<8}"
    typer.echo("=" * 50)
    typer.echo(header)
    typer.echo("-" * 50)
    for entry in stocks:
        ticker = entry.get("ticker", "")
        name = entry.get("name", "")
        priority = str(entry.get("priority", ""))
        alert_count = str(len(entry.get("alerts", {})))
        typer.echo(f"{ticker:<10} {name:<16} {priority:<8} {alert_count:<8}")
    typer.echo("=" * 50)


@watchlist_app.command()
def get(
    ticker: str = typer.Argument(..., help="股票代码。例如: 600519"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
) -> None:
    """查看单只股票的监视信息。"""
    output_mode = output.strip().lower()
    if output_mode not in ("text", "json"):
        typer.echo(f"错误: --output 必须为 'text' 或 'json'，收到: '{output}'", err=True)
        raise typer.Exit(code=1)

    mgr = WatchlistManager()
    entry = mgr.get(ticker)

    if entry is None:
        typer.echo(f"未找到: {ticker}", err=True)
        raise typer.Exit(code=1)

    if output_mode == "json":
        typer.echo(json.dumps(entry, ensure_ascii=False, indent=2))
        return

    typer.echo(f"代码:   {entry['ticker']}")
    typer.echo(f"名称:   {entry.get('name', '')}")
    typer.echo(f"优先级: {entry.get('priority', '')}")
    alerts = entry.get("alerts", {})
    if alerts:
        typer.echo("告警条件:")
        for key, value in alerts.items():
            typer.echo(f"  {key}: {value}")
    else:
        typer.echo("告警条件: 无")


@watchlist_app.command(name="set-alert")
def set_alert(
    ticker: str = typer.Argument(..., help="股票代码。例如: 600519"),
    price_above: Optional[float] = typer.Option(None, "--price-above", help="价格上限告警"),
    price_below: Optional[float] = typer.Option(None, "--price-below", help="价格下限告警"),
    rsi_oversold: bool = typer.Option(False, "--rsi-oversold", help="RSI 超卖告警"),
    rsi_overbought: bool = typer.Option(False, "--rsi-overbought", help="RSI 超买告警"),
    volume_surge: Optional[float] = typer.Option(None, "--volume-surge", help="成交量激增倍数告警"),
    ma_cross: bool = typer.Option(False, "--ma-cross", help="均线交叉告警"),
) -> None:
    """为股票设置告警条件。"""
    mgr = WatchlistManager()
    entry = mgr.get(ticker)
    if entry is None:
        typer.echo(f"未找到: {ticker}。请先用 'add' 命令添加。", err=True)
        raise typer.Exit(code=1)

    alerts_set = []
    if price_above is not None:
        mgr.set_alert(ticker, "price_above", price_above)
        alerts_set.append(f"price_above={price_above}")
    if price_below is not None:
        mgr.set_alert(ticker, "price_below", price_below)
        alerts_set.append(f"price_below={price_below}")
    if rsi_oversold:
        mgr.set_alert(ticker, "rsi_oversold", True)
        alerts_set.append("rsi_oversold=true")
    if rsi_overbought:
        mgr.set_alert(ticker, "rsi_overbought", True)
        alerts_set.append("rsi_overbought=true")
    if volume_surge is not None:
        mgr.set_alert(ticker, "volume_surge", volume_surge)
        alerts_set.append(f"volume_surge={volume_surge}")
    if ma_cross:
        mgr.set_alert(ticker, "ma_cross", True)
        alerts_set.append("ma_cross=true")

    if alerts_set:
        typer.echo(f"已为 {ticker} 设置告警: {', '.join(alerts_set)}")
    else:
        typer.echo(f"未指定任何告警条件。", err=True)
        raise typer.Exit(code=1)


@watchlist_app.command(name="remove-alert")
def remove_alert(
    ticker: str = typer.Argument(..., help="股票代码。例如: 600519"),
    price_above: bool = typer.Option(False, "--price-above", help="移除价格上限告警"),
    price_below: bool = typer.Option(False, "--price-below", help="移除价格下限告警"),
    rsi_oversold: bool = typer.Option(False, "--rsi-oversold", help="移除 RSI 超卖告警"),
    rsi_overbought: bool = typer.Option(False, "--rsi-overbought", help="移除 RSI 超买告警"),
    volume_surge: bool = typer.Option(False, "--volume-surge", help="移除成交量激增告警"),
    ma_cross: bool = typer.Option(False, "--ma-cross", help="移除均线交叉告警"),
) -> None:
    """移除股票的告警条件。"""
    mgr = WatchlistManager()
    entry = mgr.get(ticker)
    if entry is None:
        typer.echo(f"未找到: {ticker}", err=True)
        raise typer.Exit(code=1)

    removed = []
    if price_above:
        if mgr.remove_alert(ticker, "price_above"):
            removed.append("price_above")
    if price_below:
        if mgr.remove_alert(ticker, "price_below"):
            removed.append("price_below")
    if rsi_oversold:
        if mgr.remove_alert(ticker, "rsi_oversold"):
            removed.append("rsi_oversold")
    if rsi_overbought:
        if mgr.remove_alert(ticker, "rsi_overbought"):
            removed.append("rsi_overbought")
    if volume_surge:
        if mgr.remove_alert(ticker, "volume_surge"):
            removed.append("volume_surge")
    if ma_cross:
        if mgr.remove_alert(ticker, "ma_cross"):
            removed.append("ma_cross")

    if removed:
        typer.echo(f"已为 {ticker} 移除告警: {', '.join(removed)}")
    else:
        typer.echo(f"未指定要移除的告警或告警不存在。", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    watchlist_app()
