"""Archive commands for TradingAgents CLI.

Usage:
    tradingagents archive list --ticker 600519
    tradingagents archive get 2026/05/09/morning-scan_600519
    tradingagents archive search "放量突破"
    tradingagents archive summary 600519
    tradingagents archive rebuild-index
"""

from __future__ import annotations

import datetime
import json
from typing import Optional

import typer

from tradingagents.analysis_archive import AnalysisArchive


def _get_archive() -> AnalysisArchive:
    """Get the AnalysisArchive instance (lazy, uses default dir)."""
    return AnalysisArchive()


archive_app = typer.Typer(
    name="archive",
    help="查询和管理分析结果存档。",
    add_completion=False,
)


@archive_app.command()
def list_entries(
    ticker: Optional[str] = typer.Option(None, "--ticker", "-t", help="股票代码过滤"),
    decision: Optional[str] = typer.Option(None, "--decision", "-d", help="决策方向过滤 (buy/hold/sell)"),
    entry_type: Optional[str] = typer.Option(None, "--type", help="条目类型过滤 (morning-scan/evening-review/batch)"),
    days: int = typer.Option(30, "--days", help="回溯天数"),
    limit: int = typer.Option(20, "--limit", "-l", help="最大返回条数"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "json" 或 "text"'),
):
    """列出存档中的分析条目，支持多种过滤条件。"""
    archive = _get_archive()
    date_from = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

    entries = archive.list(
        ticker=ticker,
        date_from=date_from,
        decision=decision,
        entry_type=entry_type,
        limit=limit,
    )

    if output == "json":
        typer.echo(json.dumps(entries, ensure_ascii=False, indent=2))
        return


    if not entries:
        typer.echo("没有匹配的存档条目。")
        return

    typer.echo(f"找到 {len(entries)} 条记录:")
    typer.echo("-" * 80)
    for e in entries:
        tags_str = ", ".join(e.get("tags", []) or [])
        typer.echo(f"  ID:       {e['id']}")
        typer.echo(f"  日期:     {e['date']}")
        typer.echo(f"  类型:     {e['type']}")
        typer.echo(f"  股票:     {e['ticker']}")
        typer.echo(f"  决策:     {e['decision']}")
        if tags_str:
            typer.echo(f"  标签:     {tags_str}")
        typer.echo("-" * 80)


@archive_app.command()
def get_entry(
    entry_id: str = typer.Argument(..., help="条目 ID (格式: YYYY/MM/DD/type_ticker)"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "json" 或 "text"'),
):
    """获取存档中的完整分析条目内容。"""
    archive = _get_archive()
    entry = archive.get(entry_id)

    if entry is None:
        typer.echo(f"错误: 未找到条目 '{entry_id}'", err=True)
        raise typer.Exit(code=1)

    if output == "json":
        typer.echo(json.dumps(entry, ensure_ascii=False, indent=2))
        return


    meta = entry.get("_meta", {})
    request = entry.get("request", {})
    analysis = entry.get("analysis", {})

    typer.echo(f"条目 ID:   {meta.get('id', entry_id)}")
    typer.echo(f"存档时间: {meta.get('archived_at', 'N/A')}")
    typer.echo(f"命令来源: {meta.get('source_command', 'N/A')}")
    typer.echo(f"股票代码: {request.get('ticker', 'N/A')}")
    typer.echo(f"分析日期: {request.get('date', 'N/A')}")
    typer.echo(f"最终决策: {analysis.get('final_decision', 'N/A')}")
    typer.echo(f"评级:     {analysis.get('rating', 'N/A')}")
    typer.echo("")
    typer.echo("--- 分析推理 ---")
    reasoning = analysis.get("reasoning", "（无详细推理）")
    typer.echo(reasoning)

    signals = analysis.get("signals", {})
    if signals:
        typer.echo("")
        typer.echo("--- 信号详情 ---")
        for analyst, signal in signals.items():
            typer.echo(f"\n{analyst}:")
            typer.echo(f"  方向:   {signal.get('direction', 'N/A')}")
            typer.echo(f"  摘要:   {signal.get('summary', 'N/A')}")


@archive_app.command()
def search_entries(
    query: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(20, "--limit", "-l", help="最大返回条数"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "json" 或 "text"'),
):
    """全文搜索存档中的分析内容。"""
    archive = _get_archive()
    results = archive.search(query, limit=limit)

    if output == "json":
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not results:
        typer.echo(f"未找到包含 '{query}' 的条目。")
        return

    typer.echo(f"找到 {len(results)} 条匹配 '{query}' 的记录:")
    typer.echo("-" * 80)
    for e in results:
        typer.echo(f"  ID:       {e['id']}")
        typer.echo(f"  日期:     {e['date']}")
        typer.echo(f"  类型:     {e['type']}")
        typer.echo(f"  股票:     {e['ticker']}")
        typer.echo(f"  决策:     {e['decision']}")
        typer.echo("-" * 80)


@archive_app.command()
def ticker_summary(
    ticker: str = typer.Argument(..., help="股票代码"),
    days: int = typer.Option(90, "--days", "-d", help="统计回溯天数"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "json" 或 "text"'),
):
    """查看某只股票的历史信号分布汇总。"""
    archive = _get_archive()
    summary = archive.summary(ticker, days=days)

    if output == "json":
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    typer.echo(f"股票:     {ticker}")
    typer.echo(f"统计周期: 最近 {days} 天")
    typer.echo(f"总条目数: {summary['total_entries']}")
    typer.echo("")

    if summary['total_entries'] == 0:
        typer.echo("该时间段内无存档记录。")
        return

    typer.echo("--- 决策分布 ---")
    for decision, count in sorted(summary['by_decision'].items()):
        bar = "█" * count
        typer.echo(f"  {decision:<12} {count:>3}  {bar}")

    typer.echo("")
    typer.echo("--- 条目类型分布 ---")
    for etype, count in sorted(summary['by_type'].items()):
        bar = "█" * count
        typer.echo(f"  {etype:<20} {count:>3}  {bar}")


@archive_app.command()
def rebuild_index():
    """从存档文件完全重建索引。"""
    archive = _get_archive()
    count = archive.rebuild_index()
    typer.echo(f"索引重建完成，共 {count} 条记录。")



def save_to_archive(
    result: dict,
    entry_type: str,
    ticker: str,
    date: str,
    config: dict = None,
) -> Optional[str]:
    """Save an analysis result dict to the archive.
    
    This is the integration hook called by CLI commands after analysis
    completes. It silently returns None on failure so it never blocks
    the main command flow.
    
    Args:
        result: Analysis result dict. Expected keys vary by command:
            - scan commands: decision, summary, current_price, change_pct, etc.
            - batch command: full final_state from TradingAgentsGraph
        entry_type: Source command name: "morning-scan", "evening-review",
                    "scan-watchlist", or "batch"
        ticker: Stock ticker symbol
        date: Analysis date in YYYY-MM-DD format
        config: Optional config dict (for archive directory path)
    
    Returns:
        Entry ID string on success, None on failure (never raises).
    """
    try:
        from tradingagents.analysis_archive import AnalysisArchive
        
        archive = AnalysisArchive(config)
        
        # Determine analysts from result
        analysts = result.get("analysts", [])
        if not analysts and "analyst_reports" in result:
            analysts = list(result["analyst_reports"].keys())
        
        # Build the archive-compatible result dict
        archive_result = {
            "request": {
                "ticker": ticker,
                "date": date,
                "analysts": analysts,
                "llm_provider": result.get("llm_provider", ""),
                "config_snapshot": {
                    "market_type": (config or {}).get("market_type", "A_SHARE"),
                },
            },
            "analysis": {
                "signals": {},
                "final_decision": result.get("decision", ""),
                "rating": result.get("decision", ""),
                "reasoning": result.get("summary", "") or "",
            },
            "tags": result.get("tags", []),
            "raw_output": {},
        }
        
        # Include market context if available
        market_context = {}
        for key in ("current_price", "change_pct", "change", "volume", "turnover",
                     "open", "high", "low", "prev_close"):
            if key in result and result[key] is not None:
                market_context[key] = result[key]
        if market_context:
            archive_result["market_context"] = market_context
        
        # For batch command, include all analyst reports
        if "analyst_reports" in result:
            archive_result["request"]["analysts"] = list(result["analyst_reports"].keys())
            signal_details = {}
            for analyst_key, report_text in result["analyst_reports"].items():
                if report_text:
                    signal_details[analyst_key] = {
                        "direction": result.get("decision", ""),
                        "summary": str(report_text)[:500],
                    }
            if signal_details:
                archive_result["analysis"]["signals"] = signal_details
        
        return archive.save(archive_result, entry_type)
    except Exception:
        return None


if __name__ == "__main__":
    archive_app()
