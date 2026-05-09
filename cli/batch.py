"""
Non-interactive batch analysis command for TradingAgents CLI.

All parameters are passed via CLI options (no interactive prompts).
Reuses TradingAgentsGraph + Propagator but without Rich terminal UI.

Usage:
    python -m cli.batch --ticker 600519
    python -m cli.batch --ticker 600519 --output json
    python -m cli.batch --ticker 600519 --output silent
    python -m cli.batch --ticker 600519 --date 2026-05-06 --analysts market,news --output json
"""

from __future__ import annotations

import datetime
import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.enterprise", override=False)

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.position_utils import calc_position_pnl
from cli.stats_handler import StatsCallbackHandler
from cli.archive import save_to_archive

ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_VALID_VALUES = set(ANALYST_ORDER)

ANALYST_ALIASES: Dict[str, str] = {
    "technical": "fundamentals",
}

ANALYST_JSON_KEYS: Dict[str, str] = {
    "market": "market",
    "social": "social",
    "news": "news",
    "fundamentals": "technical",
}

ANALYST_REPORT_MAP: Dict[str, str] = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}

RATING_DIRECTION_MAP: Dict[str, str] = {
    "Buy": "buy",
    "Overweight": "buy",
    "Hold": "hold",
    "Underweight": "sell",
    "Sell": "sell",
}

app = typer.Typer(
    name="tradingagents-batch",
    help="TradingAgents Batch: Non-interactive batch analysis.",
    add_completion=False,
    hidden=True,
)


class BatchJSONEncoder(json.JSONEncoder):

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        try:
            return float(obj)
        except (TypeError, ValueError):
            return str(obj)


def _parse_analysts(raw: str) -> List[str]:
    if not raw.strip():
        return list(ANALYST_ORDER)

    selected: List[str] = []
    for item in raw.split(","):
        key = ANALYST_ALIASES.get(item.strip().lower(), item.strip().lower())
        if key in ANALYST_VALID_VALUES and key not in selected:
            selected.append(key)

    if not selected:
        return list(ANALYST_ORDER)

    return [a for a in ANALYST_ORDER if a in selected]


def _sanitize_for_json(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if isinstance(value, (set, frozenset)):
        return list(value)

    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}

    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _build_json_output(
    final_state: Dict[str, Any],
    decision: str,
    ticker: str,
    date: str,
    cost_price: float,
    quantity: int,
) -> str:
    analyst_reports: Dict[str, Optional[str]] = {}
    for analyst_key in ANALYST_ORDER:
        json_key = ANALYST_JSON_KEYS.get(analyst_key, analyst_key)
        report_key = ANALYST_REPORT_MAP.get(analyst_key)
        if report_key:
            analyst_reports[json_key] = final_state.get(report_key, "")

    position: Dict[str, Any] = {
        "cost_price": cost_price,
        "quantity": quantity,
        "pnl_pct": None,
    }
    if cost_price > 0 and quantity > 0:
        current_price = final_state.get("current_price", 0.0)
        if current_price:
            pnl = calc_position_pnl(current_price, cost_price, quantity)
            position["pnl_pct"] = pnl.get("pnl_pct")
            position["pnl_amount"] = pnl.get("pnl_amount")
            position["current_price"] = current_price

    output: Dict[str, Any] = {
        "ticker": ticker,
        "date": date,
        "status": "completed",
        "analyst_reports": analyst_reports,
        "investment_plan": final_state.get("investment_plan", ""),
        "trader_plan": final_state.get("trader_investment_plan", ""),
        "final_decision": {
            "rating": decision,
            "reasoning": final_state.get("final_trade_decision", ""),
        },
        "position": position,
        "signals": {
            "rating": decision,
            "direction": RATING_DIRECTION_MAP.get(decision, "hold"),
        },
    }

    cleaned = _deep_sanitize(output)
    return json.dumps(cleaned, ensure_ascii=False, indent=2, cls=BatchJSONEncoder)


def _deep_sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _deep_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [_deep_sanitize(v) for v in obj]
    return _sanitize_for_json(obj)


def _format_text_output(
    final_state: Dict[str, Any],
    decision: str,
    stats_handler: StatsCallbackHandler,
    ticker: str,
    date: str,
) -> str:
    lines: List[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append(f"  TradingAgents Batch Analysis")
    lines.append(sep)
    lines.append(f"  Ticker:      {ticker}")
    lines.append(f"  Date:        {date}")
    lines.append(f"  Decision:    {decision}")
    lines.append(f"  Direction:   {RATING_DIRECTION_MAP.get(decision, 'hold')}")
    lines.append(sep)

    stats = stats_handler.get_stats()
    lines.append(f"  LLM calls:   {stats['llm_calls']}")
    lines.append(f"  Tool calls:  {stats['tool_calls']}")
    tokens_in = stats["tokens_in"]
    tokens_out = stats["tokens_out"]
    if tokens_in > 0 or tokens_out > 0:
        lines.append(f"  Tokens:      {tokens_in} in / {tokens_out} out")
    lines.append(sep)

    for analyst_key in ANALYST_ORDER:
        report_key = ANALYST_REPORT_MAP.get(analyst_key)
        if not report_key:
            continue
        content = final_state.get(report_key, "")
        if content:
            title = ANALYST_JSON_KEYS.get(analyst_key, analyst_key).title()
            lines.append(f"\n--- {title} Analyst ---")
            lines.append(_truncate_text(content, 200))

    investment_plan = final_state.get("investment_plan", "")
    if investment_plan:
        lines.append(f"\n--- Investment Plan ---")
        lines.append(_truncate_text(investment_plan, 300))

    trader_plan = final_state.get("trader_investment_plan", "")
    if trader_plan:
        lines.append(f"\n--- Trader Plan ---")
        lines.append(_truncate_text(trader_plan, 300))

    final_decision = final_state.get("final_trade_decision", "")
    if final_decision:
        lines.append(f"\n--- Final Decision ---")
        lines.append(_truncate_text(final_decision, 500))

    lines.append(f"\n{sep}")
    return "\n".join(lines)


def _truncate_text(text: str, max_len: int = 200) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


logger = logging.getLogger(__name__)


def _graphify_auto_sync(config: dict) -> None:
    """Run graphify update . after analysis if auto_sync is enabled.

    Silently skips if graphify is not installed or the command fails.
    """
    if not config.get("graphify_auto_sync", False):
        return
    try:
        result = subprocess.run(
            ["graphify", "update", "."],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            logger.info("Graphify auto-sync: OK")
        else:
            logger.warning(
                "Graphify auto-sync: exited %d: %s",
                result.returncode, result.stderr.strip() or result.stdout.strip(),
            )
    except FileNotFoundError:
        logger.info("Graphify not installed — skipping auto-sync")
    except Exception as exc:
        logger.warning("Graphify auto-sync failed: %s", exc)


def build_config(
    llm_provider: Optional[str] = None,
    deep_model: Optional[str] = None,
    quick_model: Optional[str] = None,
    debate_rounds: Optional[int] = None,
    backend_url: Optional[str] = None,
) -> Dict[str, Any]:
    config = DEFAULT_CONFIG.copy()

    if llm_provider:
        config["llm_provider"] = llm_provider.lower()

    if deep_model:
        config["deep_think_llm"] = deep_model

    if quick_model:
        config["quick_think_llm"] = quick_model

    if debate_rounds is not None:
        config["max_debate_rounds"] = debate_rounds
        config["max_risk_discuss_rounds"] = debate_rounds

    if backend_url:
        config["backend_url"] = backend_url

    return config


@app.command()
def batch(
    ticker: str = typer.Option(
        ..., "--ticker", "-t", help="股票代码（必填）。例如: 600519"
    ),
    date: str = typer.Option(
        datetime.datetime.now().strftime("%Y-%m-%d"),
        "--date", "-d",
        help="分析日期 YYYY-MM-DD（默认今天）",
    ),
    analysts: str = typer.Option(
        ",".join(ANALYST_ORDER),
        "--analysts", "-a",
        help="逗号分隔的分析师类型: market,news,social,fundamentals（或 technical 别名）",
    ),
    llm: Optional[str] = typer.Option(
        None,
        "--llm",
        help="LLM 供应商（默认使用配置文件中的值）",
    ),
    deep_model: Optional[str] = typer.Option(
        None,
        "--deep-model",
        help="深度推理模型（默认使用配置文件中的值）",
    ),
    quick_model: Optional[str] = typer.Option(
        None,
        "--quick-model",
        help="快速推理模型（默认使用配置文件中的值）",
    ),
    debate_rounds: int = typer.Option(
        1,
        "--debate-rounds", "-r",
        help="辩论轮次（默认 1）",
    ),
    cost_price: float = typer.Option(
        0.0,
        "--cost-price",
        help="持仓成本价（可选）",
    ),
    quantity: int = typer.Option(
        0,
        "--quantity", "-q",
        help="持仓股数（可选）",
    ),
    opened_date: str = typer.Option(
        "",
        "--opened-date",
        help="开仓日期 YYYY-MM-DD（可选）",
    ),
    output: str = typer.Option(
        "text",
        "--output", "-o",
        help='输出格式: "json", "text", 或 "silent"（默认 text）',
    ),
    backend_url: Optional[str] = typer.Option(
        None,
        "--backend-url",
        help="LLM 后端 URL（覆盖默认值）",
    ),
) -> None:
    """非交互式批量分析命令。所有参数通过命令行传入，无需交互输入。"""

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

    selected_analysts = _parse_analysts(analysts)

    config = build_config(
        llm_provider=llm,
        deep_model=deep_model,
        quick_model=quick_model,
        debate_rounds=debate_rounds,
        backend_url=backend_url,
    )

    stats_handler = StatsCallbackHandler()

    try:
        # propagate() handles past context, position persistence,
        # A-share limit prices, state logging, memory updates,
        # and position auto-update — no need for manual orchestration.
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

        # --- Archive the result ---
        save_to_archive(
            {
                "decision": decision,
                "summary": final_state.get("final_trade_decision", ""),
                "analysts": selected_analysts,
                "analyst_reports": {
                    k: final_state.get(v, "")
                    for k, v in ANALYST_REPORT_MAP.items()
                },
            },
            "batch",
            ticker,
            date,
            config,
        )

        _graphify_auto_sync(config)
    except Exception as exc:
        if output_mode == "json":
            typer.echo(json.dumps(
                {"ticker": ticker, "date": date, "status": "error", "error": str(exc)},
                ensure_ascii=False, indent=2,
            ))
        elif output_mode == "text":
            typer.echo(f"分析失败: {exc}", err=True)
        raise typer.Exit(code=1)

    if output_mode == "json":
        typer.echo(_build_json_output(final_state, decision, ticker, date, cost_price, quantity))
    elif output_mode == "text":
        typer.echo(_format_text_output(final_state, decision, stats_handler, ticker, date))


if __name__ == "__main__":
    app()
