"""Real-time stock quote command for TradingAgents CLI.

Usage:
    tradingagents quote 600519
    tradingagents quote 600519,000858 --output json
"""
from typing import Optional
import json
import sys
import typer
from rich.console import Console
from rich.table import Table
from tradingagents.dataflows.akshare import get_real_time_quotes

console = Console()


def quote_command(
    symbol: str = typer.Argument(..., help="A 股代码，多只股票用逗号分隔（如 600519,000858）"),
    output: str = typer.Option("text", "--output", "-o", help='输出格式: "text" 或 "json"'),
):
    """获取 A 股实时行情。"""
    raw = get_real_time_quotes(symbol)

    if output == "json":
        # Parse the markdown output and build a structured result
        lines = raw.strip().split("\n")
        result = {"symbol": symbol, "raw_markdown": raw}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    console.print(raw)


if __name__ == "__main__":
    typer.run(quote_command)
