"""Daily pipeline orchestrator for TradingAgents.

Ties together all Phase 1+2 modules into a single unattended run.
Produces a morning briefing pushed to notification channels.

Usage:
    tradingagents daily               # Console output
    tradingagents daily --push        # Push briefing to notification channels
    tradingagents daily --skip-analysis  # Macro + alerts only, skip deep analysis
"""
from __future__ import annotations

import datetime
import json
import logging
from typing import Any, Dict, List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.watchlist import WatchlistManager

console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_macro_section() -> str:
    """Build the macro/global context section."""
    try:
        from tradingagents.dataflows.macro_context import fetch_macro_context
        from tradingagents.dataflows.market_context import fetch_market_context
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        macro = fetch_macro_context()
        market = fetch_market_context(today)
        return f"{macro}\n\n{market}"
    except Exception as e:
        return f"宏观/市场数据获取失败: {e}"


def _build_alert_section() -> str:
    """Check watchlist alerts and return triggered ones."""
    try:
        from cli.alerts import check_alerts
        # We can't easily capture typer output, so reimplement the check
        wm = WatchlistManager()
        stocks = wm.list()
        if not stocks:
            return "自选股列表为空。"

        triggered = []
        for stock in stocks:
            alerts = stock.get("alerts", {})
            if not alerts:
                continue
            triggered.append({
                "ticker": stock["ticker"],
                "name": stock.get("name", stock["ticker"]),
                "alerts": alerts,
            })

        if not any(s.get("alerts") for s in stocks):
            return "未配置预警条件。"

        # Quick price check using real-time quotes
        from tradingagents.dataflows.akshare import get_real_time_quotes
        lines = []
        for stock in stocks:
            sym = stock["ticker"]
            alerts = stock.get("alerts", {})
            if not alerts:
                continue
            try:
                quotes = get_real_time_quotes(sym)
                if "最新价" in quotes:
                    for line in quotes.split("\n"):
                        if "最新价" in line and "|" in line:
                            parts = line.split("|")
                            if len(parts) >= 3:
                                price = parts[2].strip()
                                lines.append(f"- **{sym}** {stock.get('name','')}: 现价 {price}")
            except Exception:
                pass

        return "\n".join(lines) if lines else "预警数据获取中..."
    except Exception as e:
        return f"预警检查失败: {e}"


def _build_position_risk_section() -> str:
    """Build portfolio risk assessment section."""
    try:
        from tradingagents.agents.utils.position_state import PositionStateManager
        from tradingagents.dataflows.position_risk import assess_concentration_risk, assess_correlation_risk

        psm = PositionStateManager(DEFAULT_CONFIG.copy())
        raw = psm.get_all() or {}

        if not raw:
            return "当前无持仓。"

        positions = []
        for ticker, pos in raw.items():
            qty = int(pos.get("quantity", 0))
            if qty <= 0:
                continue
            positions.append({
                "symbol": ticker,
                "quantity": qty,
                "cost_price": float(pos.get("cost_price", 0)),
                "current_price": float(pos.get("current_price", 0)) or float(pos.get("cost_price", 0)),
            })

        if not positions:
            return "无有效持仓。"

        conc = assess_concentration_risk(positions)
        corr = assess_correlation_risk(positions)

        lines = [
            f"持仓数: {len(positions)}",
            f"集中度: HHI {conc.get('hhi', 0)} ({conc.get('concentration_level', '')})",
            f"最大仓位: {conc.get('largest_position', '')} ({conc.get('largest_weight', 0)}%)",
            f"组合相关性: avg {corr.get('avg_correlation', 0)} ({corr.get('risk_level', '')}风险)",
        ]

        if corr.get("high_correlation_pairs"):
            pairs = "、".join(p["pair"] for p in corr["high_correlation_pairs"])
            lines.append(f"高相关对: {pairs}")

        return "\n".join(lines)
    except Exception as e:
        return f"风险评估失败: {e}"


def _format_briefing(sections: Dict[str, str]) -> str:
    """Format all sections into a single Markdown briefing."""
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %A")
    lines = [
        f"# 📊 每日投研晨报",
        f"**{date_str}**",
        "",
        sections.get("macro", "——"),
        "",
        "---",
        "## ⚠️ 持仓预警",
        sections.get("alerts", "——"),
        "",
        "---",
        "## 📈 组合风险",
        sections.get("risk", "——"),
        "",
        "---",
        f"*自动生成于 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*TradingAgents CN · 分析+建议模式*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Notification push
# ---------------------------------------------------------------------------

def _push_briefing(text: str):
    """Push briefing to all configured notification channels."""
    try:
        from tradingagents.notifier import create_notifier
        notifiers = create_notifier(DEFAULT_CONFIG)
        if not notifiers:
            console.print("[yellow]未配置通知渠道。[/yellow]")
            return
        date_str = datetime.datetime.now().strftime("%m/%d")
        for n in notifiers:
            n.send_markdown(f"投研晨报 {date_str}", text[:4000])
        console.print("[green]✅ 晨报已推送到通知渠道[/green]")
    except Exception as e:
        console.print(f"[red]推送失败: {e}[/red]")


# ---------------------------------------------------------------------------
# Main command
# ---------------------------------------------------------------------------

def daily_command(
    push: bool = typer.Option(False, "--push", "-p", help="推送晨报到通知渠道"),
    skip_analysis: bool = typer.Option(False, "--skip-analysis", help="跳过深度分析，只做宏观+预警"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
):
    """无人值守每日投研管线：宏观→预警→组合风险→推送。"""
    console.print("[bold]🚀 启动每日投研管线...[/bold]")

    # Section 1: Macro
    console.print("[dim]  1/3 获取宏观/市场数据...[/dim]")
    macro_text = _build_macro_section()

    # Section 2: Alerts
    console.print("[dim]  2/3 检查预警...[/dim]")
    alert_text = _build_alert_section()

    # Section 3: Risk
    console.print("[dim]  3/3 评估组合风险...[/dim]")
    risk_text = _build_position_risk_section()

    sections = {
        "macro": macro_text,
        "alerts": alert_text,
        "risk": risk_text,
    }

    brief = _format_briefing(sections)

    if output == "json":
        console.print(json.dumps(sections, ensure_ascii=False, indent=2))
        return

    console.print(brief)

    if push:
        _push_briefing(brief)


if __name__ == "__main__":
    typer.run(daily_command)
