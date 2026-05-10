"""Portfolio risk assessment command for TradingAgents CLI.

Usage:
    tradingagents portfolio-risk
    tradingagents portfolio-risk --market-drop 5
    tradingagents portfolio-risk --push
"""
from __future__ import annotations

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.agents.utils.position_state import PositionStateManager
from tradingagents.dataflows.position_utils import calc_position_pnl
from tradingagents.dataflows.position_risk import assess_all_risks
from tradingagents.default_config import DEFAULT_CONFIG

console = Console()


def portfolio_risk_command(
    market_drop: float = typer.Option(3.0, "--market-drop", "-m", help="假设大盘跌幅百分比"),
    push: bool = typer.Option(False, "--push", "-p", help="推送风险评估报告"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
):
    """评估持仓风险暴露程度。"""
    output_mode = output.strip().lower()
    if output_mode not in ("text", "json"):
        console.print("[red]错误: --output 必须为 'text' 或 'json'[/red]")
        raise typer.Exit(1)

    # Read positions
    psm = PositionStateManager(DEFAULT_CONFIG.copy())
    raw_positions = psm.get_all() or {}

    if not raw_positions:
        console.print("[yellow]当前没有持仓。[/yellow]")
        return

    # Format positions for risk assessment
    positions = []
    for ticker, pos in raw_positions.items():
        qty = int(pos.get("quantity", 0))
        if qty <= 0:
            continue
        cost = float(pos.get("cost_price", 0.0))
        # Try to get current price from the position state
        current = float(pos.get("current_price", 0.0)) or cost
        positions.append({
            "symbol": ticker,
            "quantity": qty,
            "cost_price": cost,
            "current_price": current,
        })

    if not positions:
        console.print("[yellow]没有有效持仓。[/yellow]")
        return

    console.print("[bold]🔍 正在评估持仓风险...[/bold]")
    risks = assess_all_risks(positions)

    if output_mode == "json":
        console.print(json.dumps(risks, ensure_ascii=False, indent=2, default=str))
        return

    # -- Market drop risk --
    mdr = risks.get("market_drop_risk", {})
    mdr5 = risks.get("market_drop_5pct", {})

    console.print(f"\n[bold]📉 大盘下跌 {mdr.get('benchmark_drop_pct', 3.0)}% 风险暴露[/bold]")
    console.print(f"   持仓总值: [cyan]{mdr.get('total_value', 0):,.2f}[/cyan]")
    console.print(f"   预估损失: [red]{mdr.get('total_impact', 0):,.2f}[/red] "
                  f"({mdr.get('impact_pct', 0)}%)")

    if mdr.get("positions"):
        table = Table(show_header=True)
        table.add_column("股票", style="cyan")
        table.add_column("市值")
        table.add_column("Beta")
        table.add_column("预估跌幅", style="red")
        table.add_column("预估损失", style="red")
        for p in mdr["positions"]:
            table.add_row(
                p["symbol"],
                f"{p['value']:,.0f}",
                str(p.get("beta", "1.0")),
                f"{p.get('est_drop_pct', 0)}%",
                f"{p.get('est_loss', 0):,.0f}",
            )
        console.print(table)

    if mdr5.get("total_value"):
        console.print(f"\n   大盘跌 5% 场景: 预估损失 "
                      f"[red]{mdr5.get('total_impact', 0):,.2f}[/red] "
                      f"({mdr5.get('impact_pct', 0)}%)")

    # -- Concentration risk --
    conc = risks.get("concentration", {})
    console.print(f"\n[bold]🎯 持仓集中度[/bold]")
    console.print(f"   HHI: {conc.get('hhi', 0)} ("
                  f"[{'red' if conc.get('hhi', 0) > 0.2 else 'green'}]{conc.get('concentration_level', '')}[/])")
    console.print(f"   最大仓位: {conc.get('largest_position', '')} "
                  f"({conc.get('largest_weight', 0)}%)")
    console.print(f"   持仓数量: {conc.get('num_positions', 0)}")

    # -- Drawdown --
    dd = risks.get("drawdown", {})
    console.print(f"\n[bold]📊 持仓回撤风险 (20日)[/bold]")
    console.print(f"   组合最大回撤: [red]{dd.get('max_portfolio_drawdown_pct', 0)}%[/red]")

    if dd.get("per_position"):
        table = Table(show_header=True)
        table.add_column("股票", style="cyan")
        table.add_column("最大回撤", style="red")
        for p in dd["per_position"]:
            table.add_row(p["symbol"], f"{p['max_drawdown_pct']}%")
        console.print(table)

    if push:
        _push_risk_report(risks)


def _push_risk_report(risks: dict):
    """Push risk report via notification channels."""
    try:
        from tradingagents.notifier import create_notifier
        notifiers = create_notifier(DEFAULT_CONFIG)

        mdr = risks.get("market_drop_risk", {})
        conc = risks.get("concentration", {})
        dd = risks.get("drawdown", {})

        lines = [
            "# 持仓风险评估报告",
            "",
            "## 大盘下跌风险",
            f"- 持仓总值: {mdr.get('total_value', 0):,.0f}",
            f"- 跌3%场景损失: {mdr.get('total_impact', 0):,.0f} ({mdr.get('impact_pct', 0)}%)",
            "",
            "## 集中度风险",
            f"- HHI: {conc.get('hhi', 0)} ({conc.get('concentration_level', '')})",
            f"- 最大仓位: {conc.get('largest_position', '')} ({conc.get('largest_weight', 0)}%)",
            "",
            "## 回撤风险",
            f"- 组合最大回撤: {dd.get('max_portfolio_drawdown_pct', 0)}%",
        ]

        body = "\n".join(lines)
        for n in notifiers:
            n.send_markdown("持仓风险报告", body)
        console.print("[green]✅ 风险评估报告已推送[/green]")
    except Exception as e:
        console.print(f"[red]推送失败: {e}[/red]")


if __name__ == "__main__":
    typer.run(portfolio_risk_command)
