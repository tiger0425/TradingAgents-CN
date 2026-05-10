"""Abnormal market movement monitor for TradingAgents CLI.

Detects and reports unusual trading activity:
- Limit-up / limit-down pools
- 炸板 (broken limit-up)
- 天地板 (extreme swings)
- Consecutive limit moves
- Strong stocks

Usage:
    tradingagents alert-abnormal
    tradingagents alert-abnormal --date 2026-05-09 --push
    tradingagents alert-abnormal --focus 600519
"""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.dataflows.a_share_anomalies import detect_all_anomalies
from tradingagents.default_config import DEFAULT_CONFIG

console = Console()


def alert_abnormal_command(
    date: str = typer.Option(None, "--date", "-d", help="交易日期 yyyy-mm-dd（默认今天）"),
    push: bool = typer.Option(False, "--push", "-p", help="推送异动报告"),
    focus: Optional[str] = typer.Option(None, "--focus", "-f", help="重点关注某只股票"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
):
    """监控 A 股短线异动信号。"""
    from datetime import datetime
    date_str = date or datetime.now().strftime("%Y-%m-%d")

    console.print(f"[bold]⚡ 正在扫描 {date_str} 市场异动...[/bold]")
    result = detect_all_anomalies(date_str)

    if output == "json":
        console.print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    # -- Limit moves --
    lm = result.get("limit_moves", {})
    up = lm.get("limit_up", [])
    down = lm.get("limit_down", [])
    zhaban = result.get("zhaban", [])
    td = result.get("tiandiban", [])
    consec = result.get("consecutive_limits", [])

    console.print(f"\n[bold]📈 涨停: [green]{lm.get('count_up', 0)}[/green] 只  |  "
                  f"📉 跌停: [red]{lm.get('count_down', 0)}[/red] 只")
    console.print(f"💥 炸板: [yellow]{len(zhaban)}[/yellow] 只  |  "
                  f"🌋 天地板: [red]{len(td)}[/red] 只  |  "
                  f"🔥 连板(≥3): [cyan]{len(consec)}[/cyan] 只")

    if up:
        table = Table(title=f"涨停股 ({len(up)}只)", show_header=True)
        table.add_column("代码", style="cyan")
        table.add_column("名称")
        table.add_column("最新价")
        table.add_column("涨跌幅", style="green")
        table.add_column("连板数", style="yellow")
        for s in up[:20]:
            lc = s.get("limit_count", "")
            table.add_row(s["code"], s["name"], str(s["price"]), str(s["change_pct"]), str(lc))
        console.print(table)

    if down:
        table = Table(title=f"跌停股 ({len(down)}只)", show_header=True)
        table.add_column("代码", style="cyan")
        table.add_column("名称")
        table.add_column("最新价")
        table.add_column("涨跌幅", style="red")
        for s in down[:20]:
            table.add_row(s["code"], s["name"], str(s["price"]), str(s["change_pct"]))
        console.print(table)

    if zhaban:
        table = Table(title=f"炸板股 ({len(zhaban)}只)", show_header=True)
        table.add_column("代码", style="cyan")
        table.add_column("名称")
        table.add_column("炸板次数", style="yellow")
        for s in zhaban[:10]:
            table.add_row(s["code"], s["name"], str(s.get("zhaban_count", "")))
        console.print(table)

    if td:
        console.print(f"\n[bold red]⚠️ 天地板关注 ({len(td)}只)[/bold red]")
        for s in td:
            console.print(f"  {s['code']} {s['name']}")

    if consec:
        console.print(f"\n[bold cyan]🔥 连板股 (≥3板, {len(consec)}只)[/bold cyan]")
        for s in consec[:10]:
            console.print(f"  {s['code']} {s['name']} — {s.get('limit_count', '?')}连板")

    if focus:
        _check_focus(focus, result)

    if push:
        _push_anomaly_report(result, date_str)


def _check_focus(symbol: str, result: dict):
    """Check if a specific stock has any anomaly signals."""
    console.print(f"\n[bold]=== 重点关注: {symbol} ===[/bold]")
    lm = result.get("limit_moves", {})
    for pool_name, pool in [("涨停", lm.get("limit_up", [])),
                             ("跌停", lm.get("limit_down", [])),
                             ("炸板", result.get("zhaban", [])),
                             ("天地板", result.get("tiandiban", []))]:
        for s in pool:
            if s["code"] == symbol:
                console.print(f"[yellow]⚠️ {symbol} 出现在 [{pool_name}] 池中[/yellow]")


def _push_anomaly_report(result: dict, date_str: str):
    """Push anomaly report via notification channels."""
    try:
        from tradingagents.notifier import create_notifier
        notifiers = create_notifier(DEFAULT_CONFIG)

        lm = result.get("limit_moves", {})
        zhaban = result.get("zhaban", [])
        td = result.get("tiandiban", [])
        consec = result.get("consecutive_limits", [])

        lines = [
            f"# 市场异动报告 - {date_str}",
            "",
            f"- 涨停: {lm.get('count_up', 0)} 只",
            f"- 跌停: {lm.get('count_down', 0)} 只",
            f"- 炸板: {len(zhaban)} 只",
            f"- 天地板: {len(td)} 只",
            f"- 连板≥3: {len(consec)} 只",
            "",
        ]
        if zhaban:
            lines.append("### 炸板股")
            lines.extend(f"- {s['code']} {s['name']}" for s in zhaban[:5])
        if td:
            lines.append("### 天地板")
            lines.extend(f"- {s['code']} {s['name']}" for s in td)

        body = "\n".join(lines)
        for n in notifiers:
            n.send_markdown(f"异动监控 {date_str}", body)
        console.print("[green]✅ 异动报告已推送[/green]")
    except Exception as e:
        console.print(f"[red]推送失败: {e}[/red]")


if __name__ == "__main__":
    typer.run(alert_abnormal_command)
