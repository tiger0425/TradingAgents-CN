"""Analyst research report command for TradingAgents CLI.

Usage:
    tradingagents research-report 600519
    tradingagents research-report 600519 --top 10 --push
    tradingagents research-report --scan-watchlist
"""
from typing import Optional
import json
import typer
from rich.console import Console
from rich.markdown import Markdown
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.dataflows.akshare import get_research_reports
from tradingagents.default_config import DEFAULT_CONFIG

console = Console()


def _summarize_report(title: str, content: str) -> str:
    """Use quick_think_llm to summarize a research report."""
    try:
        from tradingagents.llm_clients import create_llm_client
        client = create_llm_client(
            provider=DEFAULT_CONFIG.get("llm_provider", "openai"),
            model_name=DEFAULT_CONFIG.get("quick_think_llm", "gpt-4o-mini"),
        )
        llm = client.get_llm()
        prompt = (
            "你是一位金融分析师助理。请用 5-8 句中文总结以下个股研报的核心观点。\n"
            "关注：投资评级、目标价、核心逻辑、风险提示。\n\n"
            f"研报标题：{title}\n"
            f"研报内容：{content}\n\n"
            "总结："
        )
        resp = llm.invoke([("human", prompt)])
        if hasattr(resp, "content"):
            return resp.content
        return str(resp)
    except Exception:
        return content[:300] + ("..." if len(content) > 300 else "")


def research_report_command(
    symbol: Optional[str] = typer.Argument(None, help="A 股代码"),
    top: int = typer.Option(5, "--top", "-n", help="显示最新 N 篇"),
    push: bool = typer.Option(False, "--push", "-p", help="推送到通知渠道"),
    scan_watchlist: bool = typer.Option(False, "--scan-watchlist", help="扫描全部自选股"),

):
    """获取个股最新分析师研报摘要。"""
    if scan_watchlist:
        _scan_watchlist(top, push)
        return

    if not symbol:
        console.print("[red]错误: 请提供股票代码或使用 --scan-watchlist[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]📊 正在获取 {symbol} 的研报...[/bold]")
    raw = get_research_reports(symbol, top_n=top)

    if "未找到" in raw or "Error" in raw:
        console.print(raw)
        return

    console.print(Markdown(raw))

    if push:
        _push_reports(symbol, raw)


def _scan_watchlist(top: int, push: bool):
    """Scan all watchlist stocks for recent research reports."""
    from tradingagents.watchlist import WatchlistManager
    wm = WatchlistManager()
    items = wm.get_all_watchlist_items()
    if not items:
        console.print("[yellow]自选股列表为空。[/yellow]")
        return

    all_results = []
    for item in items:
        sym = item.get("symbol", item.get("ticker", ""))
        name = item.get("name", sym)
        console.print(f"[bold]📊 {name} ({sym})...[/bold]")
        raw = get_research_reports(sym, top_n=top)
        if "未找到" in raw:
            continue
        all_results.append(raw)

    if not all_results:
        console.print("[yellow]所有自选股均无更新研报。[/yellow]")
        return

    combined = "# 自选股研报汇总\n\n" + "\n\n---\n\n".join(all_results)
    console.print(Markdown(combined))

    if push:
        _push_reports("自选股", combined)


def _push_reports(title: str, content: str):
    """Push report summary via configured notification channels."""
    try:
        from tradingagents.notifier import create_notifier
        notifiers = create_notifier(DEFAULT_CONFIG)
        for n in notifiers:
            n.send_markdown(f"研报摘要: {title}", content[:4000])
        console.print("[green]✅ 已推送到通知渠道[/green]")
    except Exception as e:
        console.print(f"[red]推送失败: {e}[/red]")


if __name__ == "__main__":
    typer.run(research_report_command)
