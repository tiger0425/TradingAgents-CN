#!/usr/bin/env python3
"""
TradingAgents Agent 批量分析 — 使用完整 LLM Agent 管线逐只分析 A 股。
每只股票走完 Market/Fundamentals/News/Social 分析师 + 多空辩论 + 风控 + 决策全流程。
输出为 Markdown 报告，存入 guping/ 目录。

用法:
    python guping/agent_batch.py                          # 分析默认7只
    python guping/agent_batch.py --tickers 600418,600733  # 自定义股票列表
    python guping/agent_batch.py --skip 0                 # 从第一只开始（默认）
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
import time
import traceback

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

# 关闭 fan_out（已知 LangGraph 拓扑冲突），串行更稳定
os.environ.pop("TRADINGAGENTS_FAN_OUT", None)

# 减少日志噪音
logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

TODAY = datetime.datetime.now().strftime("%Y-%m-%d")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")

DEFAULT_TICKERS = [
    "600418",  # 江淮汽车 — 商用载货车
    "600733",  # 北汽蓝谷 — 商用载货车
    "000796",  # 凯撒旅业 — 旅游
    "605255",  # 天普股份 — 汽车零部件
    "600105",  # 永鼎股份 — 通信线缆
    "002736",  # 国信证券 — 证券
    "000166",  # 申万宏源 — 证券
]


def analyze_single(ticker: str, output_dir: str) -> dict:
    """分析单只股票。返回 {ticker, status, filepath, elapsed, char_count, error}"""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG, apply_env_overrides
    from tradingagents.dataflows.a_stock_data import get_industry, get_company_name

    start = time.time()

    try:
        industry = get_industry(ticker) or ""
        company_name = get_company_name(ticker) or ticker
    except Exception:
        industry = ""
        company_name = ticker

    print(f"  [{ticker}] {company_name} | 行业: {industry or '未知'}", flush=True)

    config = apply_env_overrides(DEFAULT_CONFIG.copy())
    graph = TradingAgentsGraph(config=config, debug=False)

    print(f"  [{ticker}] 开始分析...", flush=True)

    try:
        final_state, decision = graph.propagate(ticker, TODAY,
            industry=industry, display_name=company_name)
    except Exception as e:
        traceback.print_exc()
        return {
            "ticker": ticker, "company_name": company_name,
            "status": "FAIL", "error": f"分析错误: {e}",
            "elapsed": time.time() - start, "char_count": 0,
        }

    elapsed = time.time() - start

    # 使用 trading_graph 自带的 build_report（无正则解析，无格式损坏风险）
    report = graph.build_report(final_state)

    if not report:
        return {
            "ticker": ticker, "company_name": company_name,
            "status": "EMPTY", "error": "无报告产出",
            "elapsed": elapsed, "char_count": 0,
        }

    # 构造文件名
    safe_name = "".join(c for c in company_name if c.isalnum() or c in "_-（）")
    filename = f"{ticker}_{safe_name}_Agent分析_{TODAY}.md"
    filepath = os.path.join(output_dir, filename)

    # 添加报告头部元信息
    header = (
        f"# 📊 {ticker} {company_name} — TradingAgents 智能分析报告\n\n"
        f"> **生成日期**: {TODAY}\n"
        f"> **分析耗时**: {elapsed:.0f} 秒\n"
        f"> **行业分类**: {industry}\n"
        f"> **引擎**: TradingAgents V1.3 (Market + Fundamentals + News + Debate + Risk + PM)\n\n"
        f"---\n\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + report)

    print(f"  [{ticker}] ✅ {elapsed:.0f}s → {filename} ({len(report)} 字)", flush=True)
    return {
        "ticker": ticker, "company_name": company_name,
        "status": "OK", "filepath": filepath,
        "elapsed": elapsed, "char_count": len(report),
    }


def main():
    parser = argparse.ArgumentParser(description="TradingAgents Agent 批量分析")
    parser.add_argument("--tickers", "-t", type=str,
                        default=",".join(DEFAULT_TICKERS),
                        help=f"股票代码 (默认: {','.join(DEFAULT_TICKERS)})")
    parser.add_argument("--output", "-o", type=str, default=OUTPUT_DIR,
                        help=f"输出目录 (默认: {OUTPUT_DIR})")
    parser.add_argument("--skip", type=int, default=0,
                        help="跳过前N只 (断点续跑)")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    output_dir = args.output
    skip = args.skip

    os.makedirs(output_dir, exist_ok=True)

    total = len(tickers) - skip
    effective_tickers = tickers[skip:]

    print(f"\n{'=' * 60}")
    print(f"  TradingAgents Agent 批量分析")
    print(f"  日期: {TODAY}")
    print(f"  股票数: {total} (跳过前 {skip} 只)")
    print(f"  列表: {', '.join(effective_tickers)}")
    print(f"  预计总耗时: ~{total * 7} 分钟")
    print(f"{'=' * 60}\n")

    results = []
    overall_start = time.time()

    for i, ticker in enumerate(effective_tickers, 1):
        actual_idx = skip + i
        print(f"\n{'─' * 40}")
        print(f"[{actual_idx}/{len(tickers)}] 正在分析 {ticker}...")
        print(f"{'─' * 40}")

        try:
            result = analyze_single(ticker, output_dir)
        except Exception as e:
            traceback.print_exc()
            result = {
                "ticker": ticker, "company_name": ticker,
                "status": "CRASH", "error": str(e),
                "elapsed": 0, "char_count": 0,
            }
        results.append(result)

    overall_elapsed = time.time() - overall_start

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"  分析完成! 总耗时: {overall_elapsed / 60:.1f} 分钟")
    print(f"{'=' * 60}")
    ok_count = 0
    for r in results:
        status_icon = {"OK": "✅", "FAIL": "❌", "CRASH": "💥", "EMPTY": "⚠️"}.get(r["status"], "❓")
        name = r.get("company_name", r["ticker"])
        if r["status"] == "OK":
            fname = os.path.basename(r.get("filepath", ""))
            print(f"  {status_icon} {r['ticker']} {name} → {fname} ({r['elapsed']:.0f}s, {r['char_count']}字)")
            ok_count += 1
        else:
            print(f"  {status_icon} {r['ticker']} {name} → {r.get('error', '未知错误')}")
    print(f"\n  成功: {ok_count}/{total}")
    print(f"  输出目录: {output_dir}")


if __name__ == "__main__":
    sys.exit(main())
