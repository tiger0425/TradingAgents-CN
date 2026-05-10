"""Stock announcement summarization command for TradingAgents CLI.

Usage:
    tradingagents notice 600519
    tradingagents notice 600519 --days 3 --type 重大事项
    tradingagents notice --scan-watchlist --push
"""
from typing import Optional
import sys
import typer
from rich.console import Console
from rich.markdown import Markdown
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.dataflows.akshare import get_individual_notices
from tradingagents.default_config import DEFAULT_CONFIG

console = Console()


def _summarize_notice(title: str, content: str) -> str:
    """Use quick_think_llm to summarize a notice. Falls back to first 200 chars."""
    try:
        from tradingagents.llm_clients import create_llm_client
        client = create_llm_client(
            provider=DEFAULT_CONFIG.get("llm_provider", "openai"),
            model_name=DEFAULT_CONFIG.get("quick_think_llm", "gpt-4o-mini"),
        )
        llm = client.get_llm()
        prompt = (
            "你是一位金融新闻分析师。请用 3-5 句中文总结以下个股公告。\n"
            "关注：发生了什么、为什么重要、对股价的潜在影响。\n\n"
            f"公告标题：{title}\n"
            f"公告内容：{content}\n\n"
            "总结："
        )
        resp = llm.invoke([("human", prompt)])
        if hasattr(resp, "content"):
            return resp.content
        return str(resp)
    except Exception:
        # Fallback: show first 200 chars
        return content[:200] + ("..." if len(content) > 200 else "")


def notice_command(
    symbol: Optional[str] = typer.Argument(None, help="A 股代码"),
    days: int = typer.Option(7, "--days", "-d", help="回溯天数"),
    notice_type: str = typer.Option("全部", "--type", "-t", help="公告类型（全部/重大事项/财务报告/风险提示等）"),
    push: bool = typer.Option(False, "--push", "-p", help="推送到通知渠道"),
    scan_watchlist: bool = typer.Option(False, "--scan-watchlist", help="扫描全部自选股公告"),
):
    """获取个股最新公告并生成 LLM 摘要。"""
    if scan_watchlist:
        _scan_watchlist(days, notice_type, push)
        return

    if not symbol:
        console.print("[red]错误: 请提供股票代码或使用 --scan-watchlist[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]📄 正在获取 {symbol} 的公告...[/bold]")

    raw = get_individual_notices(symbol, days_back=days, notice_type=notice_type)

    if "未找到" in raw or "Error" in raw:
        console.print(raw)
        return

    # LLM summarize each notice section
    sections = raw.split("\n### ")
    summarized_sections = [sections[0]]  # header

    for sec in sections[1:]:
        title_line = sec.split("\n")[0]
        title = title_line.strip()
        # Extract content after the title
        rest = "\n".join(sec.split("\n")[1:])
        # Find the announcement content
        content = ""
        in_content = False
        for line in rest.split("\n"):
            if line.strip() and "**日期**" not in line and "**类型**" not in line and "---" not in line:
                if not in_content and line.strip():
                    in_content = True
                    content += line + "\n"
                elif in_content:
                    content += line + "\n"

        content = content.strip()
        if content:
            console.print(f"[dim]  正在摘要: {title[:40]}...[/dim]")
            summary = _summarize_notice(title, content)
            sec_with_summary = f"### {title}\n{rest}\n\n**AI 摘要**: {summary}\n"
            summarized_sections.append(sec_with_summary)
        else:
            summarized_sections.append(f"### {sec}")

    result = "\n### ".join(summarized_sections)
    console.print(Markdown(result))

    if push:
        _push_notices(symbol, result)


def _scan_watchlist(days: int, notice_type: str, push: bool):
    """Scan all watchlist stocks for recent announcements."""
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
        console.print(f"[bold]📄 {name} ({sym})...[/bold]")
        raw = get_individual_notices(sym, days_back=days, notice_type=notice_type)
        if "未找到" in raw:
            continue
        all_results.append(raw)

    if not all_results:
        console.print("[yellow]所有自选股均无新公告。[/yellow]")
        return

    combined = "# 自选股公告汇总\n\n" + "\n\n---\n\n".join(all_results)
    console.print(Markdown(combined))

    if push:
        _push_notices("自选股", combined)


def _push_notices(title: str, content: str):
    """Push notice summary via configured notification channels."""
    try:
        from tradingagents.notifier import create_notifier
        notifiers = create_notifier(DEFAULT_CONFIG)
        for n in notifiers:
            n.send_markdown(f"公告摘要: {title}", content[:4000])
        console.print("[green]✅ 已推送到通知渠道[/green]")
    except Exception as e:
        console.print(f"[red]推送失败: {e}[/red]")


if __name__ == "__main__":
    typer.run(notice_command)
