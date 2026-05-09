"""Wiki commands for TradingAgents CLI.

Usage:
    tradingagents wiki generate
    tradingagents wiki generate --ticker 600519
    tradingagents wiki show 600519
    tradingagents wiki list
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

from tradingagents.analysis_archive import AnalysisArchive
from tradingagents.knowledge.wiki_generator import WikiGenerator


wiki_app = typer.Typer(
    name="wiki",
    help="生成和管理分析知识库的 Wiki 导航页面。",
    add_completion=False,
)


def _get_wiki_output_dir(output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser()
    default = os.path.join(
        os.path.expanduser("~"), ".tradingagents", "wiki"
    )
    return Path(default)


@wiki_app.command()
def generate(
    ticker: Optional[str] = typer.Option(
        None, "--ticker", "-t",
        help="仅生成指定股票代码的页面（增量更新）。",
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o",
        help="Wiki 输出目录（默认 ~/.tradingagents/wiki/）。",
    ),
):
    """生成 Wiki 导航页面。

    扫描分析存档中的所有条目，生成 Markdown 格式的导航索引：
    - wiki/index.md  — 全量概览（所有股票的索引页）
    - wiki/{ticker}.md — 各股票详情页
    - wiki/lessons.md — 跨股票经验教训

    指定 --ticker 可只更新单只股票的页面（用于增量更新）。
    """
    archive = AnalysisArchive()
    out_dir = _get_wiki_output_dir(output_dir)
    generator = WikiGenerator(archive, output_dir=str(out_dir))

    index_path = generator.generate(ticker=ticker)

    typer.echo(f"✅ Wiki 生成完成 → {index_path}")

    # Show quick summary
    entries = archive.list(limit=5)
    tickers = set(e.get("ticker", "") for e in entries)
    typer.echo(f"   覆盖 {len(tickers)} 只股票")
    typer.echo(f"   使用 `tradingagents wiki list` 查看所有页面")


@wiki_app.command()
def show(
    ticker: str = typer.Argument(..., help="要查看的股票代码。"),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o",
        help="Wiki 输出目录（默认 ~/.tradingagents/wiki/）。",
    ),
):
    """显示指定股票代码的 Wiki 详情页。"""
    out_dir = _get_wiki_output_dir(output_dir)
    page_path = out_dir / f"{ticker}.md"

    if not page_path.exists():
        typer.echo(
            f"❌ 未找到 {ticker} 的 Wiki 页面。\n"
            f"   请先运行 `tradingagents wiki generate` 生成。",
            err=True,
        )
        raise typer.Exit(code=1)

    content = page_path.read_text(encoding="utf-8")
    typer.echo(content)


@wiki_app.command()
def list_pages(
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o",
        help="Wiki 输出目录（默认 ~/.tradingagents/wiki/）。",
    ),
):
    """列出所有已生成的 Wiki 页面。"""
    out_dir = _get_wiki_output_dir(output_dir)

    if not out_dir.exists():
        typer.echo("暂无 Wiki 页面。请先运行 `tradingagents wiki generate`。")
        return

    pages = sorted(out_dir.glob("*.md"))
    if not pages:
        typer.echo("暂无 Wiki 页面。")
        return

    typer.echo(f"Wiki 页面列表 ({out_dir}):")
    typer.echo("─" * 50)
    for p in pages:
        size = p.stat().st_size
        typer.echo(f"  {p.name}  ({size:,} bytes)")
    typer.echo("─" * 50)
    typer.echo(f"共 {len(pages)} 个页面")
