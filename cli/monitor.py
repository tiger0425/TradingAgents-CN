"""Real-time alert monitoring command for TradingAgents CLI.

Reads watchlist alert conditions, checks against real-time data,
pushes notifications when triggered.

Usage:
    tradingagents monitor --once          # Single check (crontab)
    tradingagents monitor --interval 300  # Continuous polling every 5min
    tradingagents monitor --push           # Push triggered alerts
"""
from __future__ import annotations

import datetime
import json
import time
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.watchlist import WatchlistManager
from tradingagents.dataflows.akshare import get_real_time_quotes
from tradingagents.default_config import DEFAULT_CONFIG

console = Console()


# ---------------------------------------------------------------------------
# Alert checking (reuses cli/alerts.py logic where possible)
# ---------------------------------------------------------------------------

PRICE_ALERTS = {"price_above", "price_below"}


def _parse_price_from_quotes(quotes_md: str) -> Optional[float]:
    """Extract current price from get_real_time_quotes markdown output."""
    for line in quotes_md.split("\n"):
        if "最新价" in line and "|" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                val = parts[2].strip()
                try:
                    return float(val)
                except ValueError:
                    pass
        # Single stock table: | **最新价** | 1580.0 |
        if "最新价" in line:
            idx = line.rfind("|")
            if idx > 0:
                val = line[idx + 1:].strip()
                try:
                    return float(val)
                except ValueError:
                    pass
    return None


def _check_price_alert(symbol: str, price: float, alerts: dict) -> List[Dict[str, Any]]:
    """Check price above/below conditions."""
    triggered = []
    if "price_above" in alerts:
        threshold = float(alerts["price_above"])
        if price > threshold:
            triggered.append({
                "ticker": symbol,
                "alert": "price_above",
                "current": price,
                "threshold": threshold,
                "time": datetime.datetime.now().isoformat(),
            })
    if "price_below" in alerts:
        threshold = float(alerts["price_below"])
        if price < threshold:
            triggered.append({
                "ticker": symbol,
                "alert": "price_below",
                "current": price,
                "threshold": threshold,
                "time": datetime.datetime.now().isoformat(),
            })
    return triggered


def _check_alerts_for_stock(symbol: str, alerts: dict) -> List[Dict[str, Any]]:
    """Check all alert conditions for a single stock using real-time data."""
    triggered: List[Dict[str, Any]] = []

    need_price = bool(PRICE_ALERTS & set(alerts.keys()))
    if not need_price:
        return triggered

    quotes_md = get_real_time_quotes(symbol)
    if "Error" in quotes_md or "No real-time" in quotes_md:
        return triggered

    current_price = _parse_price_from_quotes(quotes_md)
    if current_price is None:
        return triggered

    triggered.extend(_check_price_alert(symbol, current_price, alerts))
    return triggered


# ---------------------------------------------------------------------------
# Notification helpers
# ---------------------------------------------------------------------------

def _push_alerts(triggered: List[Dict[str, Any]]):
    """Push triggered alerts via notification channels."""
    try:
        from tradingagents.notifier import create_notifier
        notifiers = create_notifier(DEFAULT_CONFIG)

        # Build a markdown summary
        lines = ["# 预警触发通知", "", "| 股票 | 条件 | 当前值 | 阈值 |", "|---|---|---|---|"]
        for t in triggered:
            ticker = t.get("ticker", "")
            alert_type = t.get("alert", "")
            current = t.get("current", "")
            threshold = t.get("threshold", "")
            label = {"price_above": "突破上限", "price_below": "跌破下限"}.get(alert_type, alert_type)
            lines.append(f"| {ticker} | {label} | {current} | {threshold} |")

        body = "\n".join(lines)
        for n in notifiers:
            n.send_markdown(f"预警监控 ({len(triggered)}条)", body)
    except Exception as e:
        console.print(f"[red]推送失败: {e}[/red]")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

def monitor_command(
    once: bool = typer.Option(False, "--once", help="单次检查（crontab 模式）"),
    interval: int = typer.Option(60, "--interval", "-i", help="轮询间隔（秒），仅连续模式有效"),
    push: bool = typer.Option(False, "--push", "-p", help="触发时推送通知"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
):
    """实时监控自选股价格告警条件。"""
    wm = WatchlistManager()
    stocks = wm.list()
    tickers_with_alerts = [
        s for s in stocks
        if s.get("alerts") and any(k in PRICE_ALERTS for k in s["alerts"])
    ]

    if not tickers_with_alerts:
        console.print("[yellow]没有配置价格告警的自选股。[/yellow]")
        console.print("使用 [bold]tradingagents watchlist add SYMBOL --alert price_above=1600[/bold] 添加告警")
        return

    check_count = 0

    while True:
        now = datetime.datetime.now().strftime("%H:%M:%S")
        all_triggered: List[Dict[str, Any]] = []

        for stock in tickers_with_alerts:
            symbol = stock["ticker"]
            alerts = stock.get("alerts", {})
            triggered = _check_alerts_for_stock(symbol, alerts)
            all_triggered.extend(triggered)

        check_count += 1

        if output == "json":
            result = {
                "check_time": now,
                "check_round": check_count,
                "stocks_checked": len(tickers_with_alerts),
                "alerts_triggered": len(all_triggered),
                "triggered": all_triggered,
            }
            console.print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            console.print(f"[dim][{now}] 检查 #{check_count} — "
                          f"{len(tickers_with_alerts)} 只股票，"
                          f"{len(all_triggered)} 条告警触发[/dim]")
            if all_triggered:
                table = Table(title="触发告警", show_header=True)
                table.add_column("股票", style="cyan")
                table.add_column("条件", style="yellow")
                table.add_column("当前值", style="red")
                table.add_column("阈值", style="green")
                for t in all_triggered:
                    label = {"price_above": "突破↑", "price_below": "跌破↓"}.get(
                        t["alert"], t["alert"]
                    )
                    table.add_row(t["ticker"], label, str(t["current"]), str(t["threshold"]))
                console.print(table)

        if push and all_triggered:
            _push_alerts(all_triggered)

        if once:
            break

        time.sleep(interval)


if __name__ == "__main__":
    typer.run(monitor_command)
