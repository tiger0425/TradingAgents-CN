"""
Scan commands for TradingAgents CLI: scan-watchlist, morning-scan, evening-review.

Orchestrates batch analysis across watchlist stocks and aggregates results
into structured summaries (JSON or plain text). No Rich UI.

Usage:
    python -m cli.scan scan-watchlist --date 2026-05-09
    python -m cli.scan scan-watchlist --date 2026-05-09 --output json
    python -m cli.scan morning-scan --date 2026-05-09 --output json
    python -m cli.scan evening-review --date 2026-05-09 --output json
"""

from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.watchlist import WatchlistManager
from tradingagents.notifier import create_notifier
from tradingagents.agents.utils.position_state import PositionStateManager
from tradingagents.dataflows.position_utils import calc_position_pnl
from tradingagents.dataflows.akshare import _to_sina_symbol

from cli.batch import (
    build_config,
    _parse_analysts,
    _graphify_auto_sync,
    ANALYST_ORDER,
    RATING_DIRECTION_MAP,
    BatchJSONEncoder,
    _deep_sanitize,
)
from cli.stats_handler import StatsCallbackHandler
from cli.archive import save_to_archive

# Lazy akshare import — not required for import-time, only needed at runtime
try:
    import akshare as ak

    _AKSHARE_AVAILABLE = True
except ImportError:
    ak = None  # type: ignore[assignment]
    _AKSHARE_AVAILABLE = False

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

SIGNAL_KEYS = ["buy", "overweight", "hold", "underweight", "sell"]

# ------------------------------------------------------------------
# Helpers — signal grouping & output formatting
# ------------------------------------------------------------------


def _group_signals(results: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group scan results by decision rating into signal buckets.

    Each result dict should have "ticker" and "decision" keys.
    Results with an "error" key are skipped.
    """
    signals: Dict[str, List[str]] = {k: [] for k in SIGNAL_KEYS}
    for r in results:
        if r.get("error"):
            continue
        decision = r.get("decision", "Hold")
        key = decision.lower()
        if key in signals:
            signals[key].append(r["ticker"])
    return signals


def _truncate_text(text: str, max_len: int = 100) -> str:
    """Truncate text to max_len with ellipsis."""
    if isinstance(text, str) and len(text) > max_len:
        return text[: max_len - 3] + "..."
    return str(text) if text else ""


def _format_signal_line(label: str, tickers: List[str]) -> str:
    """Format a single signal line for text output."""
    if tickers:
        return f"  {label:<13} {', '.join(tickers)}"
    return f"  {label:<13} (none)"


def _build_scan_json_output(
    date: str,
    results: List[Dict[str, Any]],
    signals: Dict[str, List[str]],
    scanned: int,
    total: int,
    **extra_fields: Any,
) -> dict:
    """Build the standard scan JSON output dict.

    extra_fields may include: quotes, positions, holdings, total_pnl
    depending on the scan type.
    """
    output: Dict[str, Any] = {
        "date": date,
        "total": total,
        "scanned": scanned,
        "signals": signals,
    }
    output.update(extra_fields)

    # Build details: one entry per result
    details: List[Dict[str, Any]] = []
    for r in results:
        detail: Dict[str, Any] = {}
        if r.get("error"):
            detail = {
                "ticker": r["ticker"],
                "status": "error",
                "error": r["error"],
            }
        else:
            detail = {
                "ticker": r["ticker"],
                "decision": r.get("decision", ""),
                "summary": _truncate_text(r.get("summary", ""), 200),
            }
            # Attach per-ticker metadata if present (price, change, pnl, etc.)
            for key in ("current_price", "change", "change_pct",
                        "cost_price", "quantity", "pnl_amount", "pnl_pct",
                        "name"):
                if key in r:
                    detail[key] = r[key]
        details.append(detail)
    output["details"] = details

    return _deep_sanitize(output)


def _format_scan_text_header(
    title: str,
    date: str,
    scanned: int,
    total: int,
) -> str:
    """Build the common text output header for all scan commands."""
    sep = "=" * 60
    lines = [
        sep,
        f"  {title}",
        sep,
        f"  Date:       {date}",
        f"  Total:      {total}  Scanned: {scanned}",
    ]
    return "\n".join(lines)


def _format_scan_text_signals(signals: Dict[str, List[str]], indent: str = "") -> str:
    """Format signal group summary for text output."""
    lines: List[str] = []
    label_map = {
        "buy": "Buy",
        "overweight": "Overweight",
        "hold": "Hold",
        "underweight": "Underweight",
        "sell": "Sell",
    }
    for key in SIGNAL_KEYS:
        lines.append(_format_signal_line(indent + label_map.get(key, key), signals.get(key, [])))
    return "\n".join(lines)


def _notify_scan_results(
    scan_type: str,
    date: str,
    signals: Dict[str, List[str]],
    scanned: int,
    total: int,
    config: Dict[str, Any],
    **extra: Any,
) -> None:
    """Send scan result notifications if notifiers are configured.

    Builds a concise markdown summary and sends to all configured
    notification channels. Failures are logged but never raised.
    """
    notifiers = create_notifier(config)
    if not notifiers:
        return

    title = f"{scan_type} - {date}"

    # Signal summary
    chn_labels = {"buy": "买入", "overweight": "增持", "hold": "持有",
                  "underweight": "减持", "sell": "卖出"}
    signal_parts: List[str] = []
    for key in SIGNAL_KEYS:
        tickers = signals.get(key, [])
        label = chn_labels.get(key, key)
        if tickers:
            signal_parts.append(f"- **{label}**: {', '.join(tickers)}")
        else:
            signal_parts.append(f"- **{label}**: (无)")
    signal_text = "\n".join(signal_parts)

    # Build content
    content_lines = [
        f"## 扫描概览",
        f"已分析: {scanned}/{total} 只股票",
        "",
        f"## 信号汇总",
        signal_text,
    ]

    total_pnl = extra.get("total_pnl")
    holdings = extra.get("holdings")
    if total_pnl is not None:
        pnl_sign = "+" if total_pnl >= 0 else ""
        content_lines.insert(1, f"## 持仓盈亏")
        content_lines.insert(2, f"日总盈亏: {pnl_sign}{total_pnl:.2f}")
        content_lines.insert(3, f"持仓数: {holdings or 0}")
        content_lines.insert(4, "")

    content = "\n".join(content_lines)

    for n in notifiers:
        try:
            n.send_markdown(title, content)
        except Exception:
            pass  # notification failure must not crash the scan


# ------------------------------------------------------------------
# akshare data helpers
# ------------------------------------------------------------------


def _get_spot_quote(ticker: str) -> Optional[Dict[str, Any]]:
    """Fetch real-time spot quote for a single A-share ticker via shared cache.

    Uses get_current_price() which maintains a 30s TTL cache on the full
    market snapshot.  Calling this for multiple tickers within the TTL window
    reuses the same cached DataFrame.

    Returns a dict with keys: name, current_price, change, change_pct,
    open, high, low, prev_close, volume, amount, timestamp.
    Returns None if akshare is unavailable or the ticker is not found.
    """
    if not _AKSHARE_AVAILABLE:
        return None
    try:
        from tradingagents.dataflows.akshare import get_current_price
        import re

        result = get_current_price(ticker)
        if not result or result.startswith("Error") or "No real-time" in result:
            return None

        name = ""
        price = 0.0
        change = 0.0
        change_pct = 0.0
        open_price = 0.0
        high = 0.0
        low = 0.0
        prev_close = 0.0
        volume = ""
        amount = ""
        timestamp = ""

        for line in result.split("\n"):
            if line.startswith("# Real-time Quote for"):
                m = re.search(r"\((.+?)\)", line)
                name = m.group(1) if m else ticker
            elif "**Current Price**" in line:
                m = re.search(r"([\d.]+)", line)
                price = float(m.group(1)) if m else 0.0
            elif "**Change**" in line:
                m = re.search(r"([\d.-]+)\s*\(([\d.-]+)%\)", line)
                if m:
                    change = float(m.group(1))
                    change_pct = float(m.group(2))
            elif "**Open**" in line:
                m = re.search(r"([\d.]+)", line)
                open_price = float(m.group(1)) if m else 0.0
            elif "**High**" in line:
                m = re.search(r"([\d.]+)", line)
                high = float(m.group(1)) if m else 0.0
            elif "**Low**" in line:
                m = re.search(r"([\d.]+)", line)
                low = float(m.group(1)) if m else 0.0
            elif "**Previous Close**" in line:
                m = re.search(r"([\d.]+)", line)
                prev_close = float(m.group(1)) if m else 0.0
            elif "**Volume**" in line:
                m = re.search(r"(.+)", line)
                if m:
                    volume = m.group(1).replace("**Volume**: ", "").strip()
            elif "**Turnover**" in line:
                m = re.search(r"(.+)", line)
                if m:
                    amount = m.group(1).replace("**Turnover**: ", "").strip()
            elif "**Data Time**" in line:
                m = re.search(r"(.+)", line)
                if m:
                    timestamp = m.group(1).replace("**Data Time**: ", "").strip()

        if price <= 0:
            return None

        return {
            "name": name or ticker,
            "current_price": price,
            "change": change,
            "change_pct": change_pct,
            "open": open_price,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "volume": volume,
            "amount": amount,
            "timestamp": timestamp,
        }
    except Exception:
        return None


def _get_close_price(ticker: str, date: str) -> Optional[float]:
    """Fetch the closing price for a ticker on a given date via akshare.

    Uses Sina daily OHLCV (front-rehab "qfq").
    Returns the close price as float, or None on failure.
    """
    if not _AKSHARE_AVAILABLE:
        return None
    try:
        sina_symbol = _to_sina_symbol(ticker)
        df = ak.stock_zh_a_daily(
            symbol=sina_symbol,
            start_date=date,
            end_date=date,
            adjust="qfq",
        )
        if df is None or df.empty:
            return None
        return float(df.iloc[0]["close"])
    except Exception:
        return None


# ------------------------------------------------------------------
# Single-stock analysis helper
# ------------------------------------------------------------------


def _run_single_analysis(
    ticker: str,
    date: str,
    config: Dict[str, Any],
    selected_analysts: List[str],
    cost_price: float = 0.0,
    quantity: int = 0,
    opened_date: str = "",
) -> Dict[str, Any]:
    """Run batch analysis for a single stock.

    Returns a result dict with keys:
        ticker, date, status, decision, summary, (error on failure)
    Never raises — errors are captured in the result dict.
    """
    stats_handler = StatsCallbackHandler()
    try:
        graph = TradingAgentsGraph(
            selected_analysts,
            config=config,
            debug=False,
            callbacks=[stats_handler],
        )
        final_state, decision = graph.propagate(
            ticker,
            date,
            cost_price=cost_price,
            quantity=quantity,
            position_opened_date=opened_date,
        )
        # Build a brief summary from the final decision reasoning
        summary = final_state.get("final_trade_decision", "")
        if not summary:
            summary = final_state.get("investment_plan", "")

        return {
            "ticker": ticker,
            "date": date,
            "status": "completed",
            "decision": decision,
            "summary": summary,
            "stats": stats_handler.get_stats(),
        }
    except Exception as exc:
        return {
            "ticker": ticker,
            "date": date,
            "status": "error",
            "error": str(exc),
        }


def _run_scan(
    tickers: List[str],
    date: str,
    config: Dict[str, Any],
    selected_analysts: List[str],
    position_states: Optional[Dict[str, dict]] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Run analysis for a list of tickers.

    Handles errors gracefully — failed tickers produce error entries
    but do not halt the scan. Returns (results, scanned_count).
    """
    position_states = position_states or {}
    results: List[Dict[str, Any]] = []
    scanned = 0

    for ticker in tickers:
        pos = position_states.get(ticker, {})
        cost_price = float(pos.get("cost_price", 0.0))
        quantity = int(pos.get("quantity", 0))
        opened_date = str(pos.get("opened_date", ""))

        result = _run_single_analysis(
            ticker,
            date,
            config,
            selected_analysts,
            cost_price=cost_price,
            quantity=quantity,
            opened_date=opened_date,
        )
        results.append(result)
        if result.get("status") == "completed":
            scanned += 1

    return results, scanned


# ------------------------------------------------------------------
# Typer app
# ------------------------------------------------------------------

scan_app = typer.Typer(
    name="scan",
    help="TradingAgents Scan: 批量监视列表扫描。scan-watchlist / morning-scan / evening-review",
    add_completion=False,
)

# Shared option decorator
_SHARED_OPTIONS = {
    "date": typer.Option(
        datetime.datetime.now().strftime("%Y-%m-%d"),
        "--date", "-d",
        help="分析日期 YYYY-MM-DD（默认今天）",
    ),
    "output": typer.Option(
        "text",
        "--output", "-o",
        help='输出格式: "json", "text", 或 "silent"',
    ),
    "llm": typer.Option(
        None,
        "--llm",
        help="LLM 供应商（覆盖配置文件）",
    ),
    "deep_model": typer.Option(
        None,
        "--deep-model",
        help="深度推理模型（覆盖配置文件）",
    ),
    "quick_model": typer.Option(
        None,
        "--quick-model",
        help="快速推理模型（覆盖配置文件）",
    ),
    "debate_rounds": typer.Option(
        1,
        "--debate-rounds", "-r",
        help="辩论轮次（默认 1）",
    ),
}


def _build_shared_config(
    date: str,
    output: str,
    llm: Optional[str],
    deep_model: Optional[str],
    quick_model: Optional[str],
    debate_rounds: int,
) -> Tuple[Dict[str, Any], str]:
    """Validate shared options and build LLM config dict.

    Returns (config, validated_output_mode).
    Raises typer.Exit on validation failure.
    """
    output_mode = output.strip().lower()
    if output_mode not in ("json", "text", "silent"):
        typer.echo(
            f"错误: --output 必须为 'json', 'text', 或 'silent'，收到: '{output}'",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        typer.echo(
            f"错误: 日期格式无效 '{date}'，请使用 YYYY-MM-DD 格式",
            err=True,
        )
        raise typer.Exit(code=1)

    config = build_config(
        llm_provider=llm,
        deep_model=deep_model,
        quick_model=quick_model,
        debate_rounds=debate_rounds,
    )
    return config, output_mode


# ------------------------------------------------------------------
# Command: scan-watchlist
# ------------------------------------------------------------------


@scan_app.command(name="scan-watchlist")
def scan_watchlist(
    date: str = _SHARED_OPTIONS["date"],
    output: str = _SHARED_OPTIONS["output"],
    llm: Optional[str] = _SHARED_OPTIONS["llm"],
    deep_model: Optional[str] = _SHARED_OPTIONS["deep_model"],
    quick_model: Optional[str] = _SHARED_OPTIONS["quick_model"],
    debate_rounds: int = _SHARED_OPTIONS["debate_rounds"],
) -> None:
    """扫描监视列表中的所有股票，生成批量分析信号汇总。

    按优先级排序每个股票，运行完整批量分析（市场/情绪/新闻/基本面），
    汇总为 JSON 或纯文本信号报告。
    """
    config, output_mode = _build_shared_config(
        date, output, llm, deep_model, quick_model, debate_rounds,
    )

    # Read watchlist
    mgr = WatchlistManager()
    stocks = mgr.list()  # already sorted by priority ascending
    tickers = [s["ticker"] for s in stocks]
    total = len(tickers)

    if total == 0:
        if output_mode == "json":
            typer.echo(json.dumps({
                "date": date, "total": 0, "scanned": 0,
                "signals": {k: [] for k in SIGNAL_KEYS}, "details": [],
            }, ensure_ascii=False, indent=2))
        elif output_mode == "text":
            typer.echo("监视列表为空。")
        return

    # Run full batch analysis
    results, scanned = _run_scan(
        tickers, date, config, selected_analysts=list(ANALYST_ORDER),
    )
    signals = _group_signals(results)

    # --- Archive ---
    for r in results:
        if r.get("status") == "completed" and not r.get("error"):
            save_to_archive(r, "scan-watchlist", r["ticker"], date, config)

    _graphify_auto_sync(config)

    if output_mode == "silent":
        return

    if output_mode == "json":
        output_data = _build_scan_json_output(date, results, signals, scanned, total)
        typer.echo(json.dumps(output_data, ensure_ascii=False, indent=2, cls=BatchJSONEncoder))
        return

    # Text output
    lines: List[str] = []
    lines.append(_format_scan_text_header(
        "TradingAgents Watchlist Scan", date, scanned, total,
    ))
    lines.append("")
    lines.append("  --- Signals ---")
    lines.append(_format_scan_text_signals(signals, indent=""))
    lines.append("")
    lines.append("  --- Details ---")
    for r in results:
        ticker = r["ticker"]
        if r.get("error"):
            lines.append(f"  {ticker} → ERROR: {_truncate_text(r['error'], 80)}")
        else:
            summary = _truncate_text(r.get("summary", ""), 100)
            lines.append(f"  {ticker} → {r.get('decision', '?')}: {summary}")
    lines.append("")
    lines.append("=" * 60)
    typer.echo("\n".join(lines))


# ------------------------------------------------------------------
# Command: morning-scan
# ------------------------------------------------------------------


@scan_app.command(name="morning-scan")
def morning_scan(
    date: str = _SHARED_OPTIONS["date"],
    output: str = _SHARED_OPTIONS["output"],
    llm: Optional[str] = _SHARED_OPTIONS["llm"],
    deep_model: Optional[str] = _SHARED_OPTIONS["deep_model"],
    quick_model: Optional[str] = _SHARED_OPTIONS["quick_model"],
    debate_rounds: int = _SHARED_OPTIONS["debate_rounds"],
) -> None:
    """晨间快速扫描：获取实时行情 + 轻量批量分析（市场+技术面，1轮辩论）。

    为监视列表中的每只股票获取最新价格和涨跌幅，
    并运行市场和技术面分析师的快速研判。
    """
    config, output_mode = _build_shared_config(
        date, output, llm, deep_model, quick_model, debate_rounds,
    )

    # Read watchlist
    mgr = WatchlistManager()
    stocks = mgr.list()
    tickers = [s["ticker"] for s in stocks]
    total = len(tickers)

    if total == 0:
        if output_mode == "json":
            typer.echo(json.dumps({
                "date": date, "total": 0, "scanned": 0,
                "signals": {k: [] for k in SIGNAL_KEYS},
                "quotes": [], "details": [],
            }, ensure_ascii=False, indent=2))
        elif output_mode == "text":
            typer.echo("监视列表为空。")
        return

    # Fetch real-time quotes for all tickers
    quotes_by_ticker: Dict[str, dict] = {}
    for ticker in tickers:
        quote = _get_spot_quote(ticker)
        if quote:
            quotes_by_ticker[ticker] = quote

    # Morning scan: market + technical analysts only
    morning_analysts = _parse_analysts("market,technical")
    results, scanned = _run_scan(
        tickers, date, config, selected_analysts=morning_analysts,
    )

    # Merge quote data into results
    for r in results:
        ticker = r["ticker"]
        q = quotes_by_ticker.get(ticker)
        if q and r.get("status") != "error":
            r["current_price"] = q["current_price"]
            r["change"] = q["change"]
            r["change_pct"] = q["change_pct"]
            r["name"] = q["name"]

    signals = _group_signals(results)

    # --- Archive ---
    for r in results:
        if r.get("status") == "completed" and not r.get("error"):
            save_to_archive(r, "morning-scan", r["ticker"], date, config)

    _graphify_auto_sync(config)

    # --- Notification ---
    _notify_scan_results("晨间扫描", date, signals, scanned, total, config)

    if output_mode == "silent":
        return

    if output_mode == "json":
        quotes_list = [
            {
                "ticker": t,
                "name": q.get("name", ""),
                "current_price": q["current_price"],
                "change": q["change"],
                "change_pct": q["change_pct"],
            }
            for t, q in quotes_by_ticker.items()
        ]
        output_data = _build_scan_json_output(
            date, results, signals, scanned, total, quotes=quotes_list,
        )
        typer.echo(json.dumps(output_data, ensure_ascii=False, indent=2, cls=BatchJSONEncoder))
        return

    # Text output
    lines: List[str] = []
    lines.append(_format_scan_text_header(
        "Morning Scan", date, scanned, total,
    ))
    lines.append("")
    lines.append(f"  {'代码':<10} {'名称':<12} {'现价':>8} {'涨跌幅':>8}  {'信号':<12}  {'摘要'}")
    lines.append("  " + "-" * 75)
    for r in results:
        ticker = r["ticker"]
        if r.get("error"):
            lines.append(f"  {ticker:<10} {'ERROR':<12} {'':>8} {'':>8}  {'FAIL':<12}  {_truncate_text(r['error'], 40)}")
        else:
            name = r.get("name", "")[:10]
            price = f"{r.get('current_price', 0):.2f}" if r.get("current_price") else "N/A"
            change_pct = r.get("change_pct")
            change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
            decision = r.get("decision", "?")
            summary = _truncate_text(r.get("summary", ""), 40)
            lines.append(f"  {ticker:<10} {name:<12} {price:>8} {change_str:>8}  {decision:<12}  {summary}")
    lines.append("")
    lines.append("  --- Signals ---")
    lines.append(_format_scan_text_signals(signals, indent=""))
    lines.append("")
    lines.append("=" * 60)
    typer.echo("\n".join(lines))


# ------------------------------------------------------------------
# Command: evening-review
# ------------------------------------------------------------------


@scan_app.command(name="evening-review")
def evening_review(
    date: str = _SHARED_OPTIONS["date"],
    output: str = _SHARED_OPTIONS["output"],
    llm: Optional[str] = _SHARED_OPTIONS["llm"],
    deep_model: Optional[str] = _SHARED_OPTIONS["deep_model"],
    quick_model: Optional[str] = _SHARED_OPTIONS["quick_model"],
    debate_rounds: int = _SHARED_OPTIONS["debate_rounds"],
) -> None:
    """晚间复盘：获取持仓状态、收盘价，计算盈亏，汇总当日分析信号。

    为监视列表中的每只股票获取当日收盘价，对比持仓成本计算浮动盈亏，
    同时运行批量分析获取最新信号。
    """
    config, output_mode = _build_shared_config(
        date, output, llm, deep_model, quick_model, debate_rounds,
    )

    # Read watchlist
    mgr = WatchlistManager()
    stocks = mgr.list()
    tickers = [s["ticker"] for s in stocks]
    total = len(tickers)

    # Read position states
    pos_mgr = PositionStateManager()
    position_states = pos_mgr.get_all()

    if total == 0:
        if output_mode == "json":
            typer.echo(json.dumps({
                "date": date, "total": 0, "holdings": 0, "total_pnl": 0.0,
                "signals": {k: [] for k in SIGNAL_KEYS},
                "positions": [], "details": [],
            }, ensure_ascii=False, indent=2))
        elif output_mode == "text":
            typer.echo("监视列表为空。")
        return

    # Run full batch analysis with position states
    results, scanned = _run_scan(
        tickers, date, config, selected_analysts=list(ANALYST_ORDER),
        position_states=position_states,
    )
    signals = _group_signals(results)

    # --- Archive ---
    for r in results:
        if r.get("status") == "completed" and not r.get("error"):
            save_to_archive(r, "evening-review", r["ticker"], date, config)

    _graphify_auto_sync(config)

    # Calculate P&L for positions — fetch closing prices
    positions: List[Dict[str, Any]] = []
    holdings_count = 0
    total_pnl = 0.0

    for ticker in tickers:
        pos = position_states.get(ticker)
        if not pos or int(pos.get("quantity", 0)) <= 0:
            continue

        cost_price = float(pos.get("cost_price", 0.0))
        quantity = int(pos.get("quantity", 0))
        if cost_price <= 0 or quantity <= 0:
            continue

        # Fetch closing price for this date
        close_price = _get_close_price(ticker, date)
        if close_price is None:
            # Fallback: try the result's current_price if available
            for r in results:
                if r["ticker"] == ticker and r.get("current_price"):
                    close_price = float(r["current_price"])
                    break

        pnl_data = calc_position_pnl(close_price or cost_price, cost_price, quantity)
        pnl_amount = pnl_data.get("pnl_amount", 0.0)
        pnl_pct = pnl_data.get("pnl_pct", 0.0)

        # Find decision from results
        decision = "Hold"
        for r in results:
            if r["ticker"] == ticker and r.get("status") != "error":
                decision = r.get("decision", "Hold")
                break

        positions.append({
            "ticker": ticker,
            "cost_price": cost_price,
            "quantity": quantity,
            "current_price": close_price,
            "pnl_amount": pnl_amount,
            "pnl_pct": pnl_pct,
            "decision": decision,
        })
        holdings_count += 1
        total_pnl += pnl_amount

    total_pnl = round(total_pnl, 2)

    # --- Notification ---
    _notify_scan_results("晚间复盘", date, signals, scanned, total, config,
                         total_pnl=total_pnl, holdings=holdings_count)

    if output_mode == "silent":
        return

    if output_mode == "json":
        output_data = _build_scan_json_output(
            date, results, signals, scanned, total,
            holdings=holdings_count,
            total_pnl=total_pnl,
            positions=positions,
        )
        typer.echo(json.dumps(output_data, ensure_ascii=False, indent=2, cls=BatchJSONEncoder))
        return

    # Text output
    lines: List[str] = []
    lines.append(_format_scan_text_header(
        "Evening Review", date, scanned, total,
    ))
    lines.append("")

    # Positions section
    if positions:
        lines.append("  --- Positions ---")
        lines.append(f"  {'代码':<10} {'成本':>8} {'现价':>8} {'股数':>6} {'盈亏':>12} {'盈亏%':>8}  {'信号'}")
        lines.append("  " + "-" * 70)
        for p in positions:
            ticker = p["ticker"]
            cost = f"{p['cost_price']:.2f}"
            close = f"{p['current_price']:.2f}" if p.get("current_price") else "N/A"
            qty = str(p["quantity"])
            pnl_str = f"{p['pnl_amount']:+.2f}"
            pnl_pct_str = f"{p['pnl_pct']:+.2%}" if p.get("pnl_pct") is not None else "N/A"
            decision = p.get("decision", "?")
            lines.append(f"  {ticker:<10} {cost:>8} {close:>8} {qty:>6} {pnl_str:>12} {pnl_pct_str:>8}  {decision}")
        lines.append("")
    else:
        lines.append("  --- Positions ---")
        lines.append("  (无持仓)")
        lines.append("")

    # Summary
    lines.append(f"  --- Summary ---")
    lines.append(f"  日总盈亏: {total_pnl:+.2f}")
    lines.append(f"  持仓数:   {holdings_count}")
    lines.append("")

    # Signals section
    lines.append("  --- Signals ---")
    lines.append(_format_scan_text_signals(signals, indent=""))
    lines.append("")
    lines.append("=" * 60)
    typer.echo("\n".join(lines))


if __name__ == "__main__":
    scan_app()
