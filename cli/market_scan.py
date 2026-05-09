"""Market snapshot scanner for TradingAgents CLI: market-scan command.

Fetches the A-share market snapshot via akshare stock_zh_a_spot() and
presents top gainers, top losers, top volume stocks, and sector performance.

Usage:
    tradingagents market-scan --top 20 --output json
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

try:
    import akshare as ak
except ImportError:
    ak = None  # type: ignore[assignment]

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]


def _sanitize_float(val: Any) -> Optional[float]:
    """Convert a value to float, or None if not convertible."""
    if val is None:
        return None
    try:
        v = float(val)
        return v if not pd.isna(v) else None  # type: ignore[union-attr]
    except (ValueError, TypeError):
        return None


def _build_stock_entry(row) -> Dict[str, Any]:
    """Build a dict entry for a single stock from a spot DataFrame row."""
    ticker = str(row.get("代码", ""))
    code = ticker[2:] if ticker.startswith(("sh", "sz", "bj")) else ticker
    return {
        "ticker": code,
        "name": str(row.get("名称", "")),
        "price": _sanitize_float(row.get("最新价")),
        "change": _sanitize_float(row.get("涨跌额")),
        "change_pct": _sanitize_float(row.get("涨跌幅")),
        "volume": _sanitize_float(row.get("成交量")),
        "amount": _sanitize_float(row.get("成交额")),
    }


def _fetch_spot_df() -> Optional[Any]:
    """Fetch stock_zh_a_spot DataFrame via DataCache spot namespace (30s TTL).

    Repeated calls within the TTL window return the cached DataFrame without
    network requests.
    """
    if ak is None:
        return None
    try:
        from tradingagents.dataflows.cache import DataCache
        from tradingagents.default_config import DEFAULT_CONFIG

        cache = DataCache(DEFAULT_CONFIG.get("data_cache_dir", "~/.tradingagents/cache"))
        return cache.get_or_fetch(
            "spot",
            "market_snapshot",
            fetcher=lambda: ak.stock_zh_a_spot(),
            ttl=30,
        )
    except Exception:
        return None


def _get_top_gainers(df, top_n: int) -> List[Dict[str, Any]]:
    """Sort by change_pct descending, return top N."""
    if "涨跌幅" not in df.columns:
        return []
    sorted_df = df.dropna(subset=["涨跌幅"]).sort_values("涨跌幅", ascending=False)
    return [_build_stock_entry(sorted_df.iloc[i]) for i in range(min(top_n, len(sorted_df)))]


def _get_top_losers(df, top_n: int) -> List[Dict[str, Any]]:
    """Sort by change_pct ascending, return top N."""
    if "涨跌幅" not in df.columns:
        return []
    sorted_df = df.dropna(subset=["涨跌幅"]).sort_values("涨跌幅", ascending=True)
    return [_build_stock_entry(sorted_df.iloc[i]) for i in range(min(top_n, len(sorted_df)))]


def _get_top_volume(df, top_n: int) -> List[Dict[str, Any]]:
    """Sort by volume descending, return top N."""
    if "成交量" not in df.columns:
        return []
    sorted_df = df.dropna(subset=["成交量"]).sort_values("成交量", ascending=False)
    return [_build_stock_entry(sorted_df.iloc[i]) for i in range(min(top_n, len(sorted_df)))]


def _get_sector_performance(top_n: int) -> List[Dict[str, Any]]:
    """Fetch industry sector performance via akshare.

    Uses stock_board_industry_name_em() if available.
    Returns empty list on any error.
    """
    if ak is None:
        return []
    try:
        ind_df = ak.stock_board_industry_name_em()
        if ind_df is None or ind_df.empty:
            return []
        if "涨跌幅" not in ind_df.columns:
            return []
        sorted_df = ind_df.dropna(subset=["涨跌幅"]).sort_values("涨跌幅", ascending=False)
        name_col = "板块名称" if "板块名称" in sorted_df.columns else sorted_df.columns[0]
        results: List[Dict[str, Any]] = []
        for i in range(min(top_n, len(sorted_df))):
            row = sorted_df.iloc[i]
            results.append({
                "sector": str(row[name_col]),
                "avg_change": _sanitize_float(row["涨跌幅"]),
                "price": _sanitize_float(row.get("最新价")),
            })
        return results
    except Exception:
        return []


def _determine_market_status(df) -> str:
    """Guess market status from spot data timestamp.

    Returns "open", "closed", or "unknown".
    """
    if df is None or df.empty:
        return "unknown"
    try:
        ts = str(df.iloc[0].get("时间戳", "")) if "时间戳" in df.columns else ""
        if ts:
            now = datetime.datetime.now()
            if now.weekday() >= 5:
                return "closed"
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=0, second=0, microsecond=0)
            if market_open <= now <= market_close:
                return "open"
            return "closed"
    except Exception:
        pass
    return "unknown"


def market_scan(
    top: int = typer.Option(
        20,
        "--top", "-n",
        help="每类显示的股票数量（默认 20）",
    ),
    output: str = typer.Option(
        "text",
        "--output", "-o",
        help='输出格式: "json", "text", 或 "silent"',
    ),
) -> None:
    """A 股市场快速扫描：涨幅榜、跌幅榜、成交量榜、板块表现。

    从 akshare 获取全市场实时快照，按涨跌幅和成交量排序，
    输出结构化 JSON 或格式化文本表格。

    示例：
        tradingagents market-scan --top 20 --output json
    """
    output_mode = output.strip().lower()
    if output_mode not in ("json", "text", "silent"):
        typer.echo(
            f"错误: --output 必须为 'json', 'text', 或 'silent'，收到: '{output}'",
            err=True,
        )
        raise typer.Exit(code=1)

    if top < 1:
        typer.echo("错误: --top 必须为正整数", err=True)
        raise typer.Exit(code=1)

    date = datetime.datetime.now().strftime("%Y-%m-%d")

    df = _fetch_spot_df()
    if df is None:
        err_msg = "无法获取市场数据，请确认 akshare 已安装且网络可用。"
        if output_mode == "json":
            typer.echo(json.dumps({
                "date": date,
                "market_status": "unknown",
                "error": err_msg,
                "top_gainers": [],
                "top_losers": [],
                "top_volume": [],
                "sector_performance": [],
            }, ensure_ascii=False, indent=2))
        else:
            typer.echo(err_msg)
        raise typer.Exit(code=1)

    market_status = _determine_market_status(df)
    top_gainers = _get_top_gainers(df, top)
    top_losers = _get_top_losers(df, top)
    top_volume = _get_top_volume(df, top)
    sector_perf = _get_sector_performance(min(top, 10))

    if output_mode == "silent":
        return

    if output_mode == "json":
        result = {
            "date": date,
            "market_status": market_status,
            "top_gainers": top_gainers,
            "top_losers": top_losers,
            "top_volume": top_volume,
            "sector_performance": sector_perf,
        }
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Text output — formatted tables
    lines: List[str] = []
    sep = "=" * 72

    lines.append(sep)
    lines.append(f"  A 股市场扫描 - {date}  状态: {market_status}")
    lines.append(sep)

    def _fmt_change(chg: Optional[float]) -> str:
        if chg is None:
            return "    N/A"
        return f"{chg:+.2f}%"

    def _fmt_price(price: Optional[float]) -> str:
        if price is None:
            return "    N/A"
        return f"{price:8.2f}"

    def _fmt_volume(vol: Optional[float]) -> str:
        if vol is None:
            return "       N/A"
        if vol >= 1e8:
            return f"{vol / 1e8:7.2f}亿"
        if vol >= 1e4:
            return f"{vol / 1e4:7.2f}万"
        return f"{vol:7.0f}手"

    # Top gainers table
    if top_gainers:
        lines.append("")
        lines.append(f"  --- 涨幅榜 TOP {len(top_gainers)} ---")
        lines.append(f"  {'代码':<8} {'名称':<12} {'现价':>8} {'涨跌额':>8} {'涨跌幅':>8}  {'成交量':>10}")
        lines.append("  " + "-" * 62)
        for s in top_gainers:
            lines.append(
                f"  {s['ticker']:<8} {s['name'][:10]:<12} "
                f"{_fmt_price(s['price'])} {_fmt_change(s['change'])} "
                f"{_fmt_change(s['change_pct'])}  {_fmt_volume(s['volume'])}"
            )

    # Top losers table
    if top_losers:
        lines.append("")
        lines.append(f"  --- 跌幅榜 TOP {len(top_losers)} ---")
        lines.append(f"  {'代码':<8} {'名称':<12} {'现价':>8} {'涨跌额':>8} {'涨跌幅':>8}  {'成交量':>10}")
        lines.append("  " + "-" * 62)
        for s in top_losers:
            lines.append(
                f"  {s['ticker']:<8} {s['name'][:10]:<12} "
                f"{_fmt_price(s['price'])} {_fmt_change(s['change'])} "
                f"{_fmt_change(s['change_pct'])}  {_fmt_volume(s['volume'])}"
            )

    # Top volume table
    if top_volume:
        lines.append("")
        lines.append(f"  --- 成交量榜 TOP {len(top_volume)} ---")
        lines.append(f"  {'代码':<8} {'名称':<12} {'现价':>8} {'涨跌幅':>8}  {'成交量':>10}")
        lines.append("  " + "-" * 48)
        for s in top_volume:
            lines.append(
                f"  {s['ticker']:<8} {s['name'][:10]:<12} "
                f"{_fmt_price(s['price'])} {_fmt_change(s['change_pct'])}  "
                f"{_fmt_volume(s['volume'])}"
            )

    # Sector performance
    if sector_perf:
        lines.append("")
        lines.append(f"  --- 板块表现 TOP {len(sector_perf)} ---")
        lines.append(f"  {'板块':<16} {'涨跌幅':>8}  {'最新价':>8}")
        lines.append("  " + "-" * 38)
        for s in sector_perf:
            lines.append(
                f"  {s['sector'][:14]:<16} "
                f"{_fmt_change(s.get('avg_change'))}  "
                f"{_fmt_price(s.get('price'))}"
            )

    lines.append("")
    lines.append(sep)
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        market_scan()
    else:
        typer.echo("用法: python -m cli.market_scan --top 20 --output json")
