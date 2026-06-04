"""TradingAgents HTTP API — uses TradingAgentsGraph unified path.

Graph pipeline unified: all entry points → TradingAgentsGraph.propagate().
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .default_config import DEFAULT_CONFIG

app = FastAPI(title="TradingAgents API")
logger = logging.getLogger(__name__)

_bootstrap_done = False


@app.on_event("startup")
async def startup():
    global _bootstrap_done
    if _bootstrap_done:
        return
    try:
        from .bootstrap import bootstrap
        bootstrap()
        _bootstrap_done = True
    except Exception as e:
        logger.warning("Bootstrap deferred: %s. Set API keys and restart.", e)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    user_id: str = "default"
    message: str
    platform: str = "unknown"
    ticker: str = ""
    trade_date: str | None = None  # "YYYY-MM-DD", None = today


class AnalyzeResponse(BaseModel):
    report: str
    intent: str = "standard_analysis"
    generation_mode: str = "direct"
    template_id: str = ""
    estimated_cost_usd: float = 0.0
    workflow_steps: int = 6
    industry_verification: dict | None = None


class StatusResponse(BaseModel):
    status: str
    kb_entries: int
    user_count: int


class PortfolioChatRequest(BaseModel):
    user_id: str = "default"
    message: str


class PortfolioChatResponse(BaseModel):
    action: str = ""
    ticker: str = ""
    name: str = ""
    cost_price: float = 0.0
    quantity: int = 0
    confirmation: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Dependency injection (set by bootstrap)
# ---------------------------------------------------------------------------

_graph: "TradingAgentsGraph | None" = None
_portfolio_mgr = None
_kb = None
_cost_tracker = None


def configure(trading_graph, portfolio_mgr=None, kb=None, cost_tracker=None):
    """Inject dependencies at startup. ``trading_graph`` is a TradingAgentsGraph instance."""
    global _graph, _portfolio_mgr, _kb, _cost_tracker
    _graph = trading_graph
    _portfolio_mgr = portfolio_mgr
    _kb = kb
    _cost_tracker = cost_tracker


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """Run full analysis pipeline via TradingAgentsGraph.propagate()."""
    graph = _resolve_graph()

    # P0-3: reject empty ticker instead of silent 000001 default
    if not req.ticker:
        raise HTTPException(status_code=400, detail="请提供 ticker（6 位 A 股代码）")
    ticker = req.ticker

    # P0-2: support user-supplied trade_date for backtesting
    from datetime import date
    trade_date = req.trade_date or date.today().isoformat()

    # P0-1: validate ticker and resolve industry/company name
    from tradingagents.dataflows.a_stock_data import validate_ticker, get_industry, get_company_name
    ok, display_name = validate_ticker(ticker)
    if not ok:
        raise HTTPException(status_code=400, detail=display_name)
    industry = ""
    try:
        industry = get_industry(ticker) or ""
    except Exception:
        pass

    final_state, decision = graph.propagate(
        ticker, trade_date, industry=industry, display_name=display_name,
    )

    # build report from state (no regex parsing, no ReportRenderer)
    report = graph.build_report(final_state)

    return AnalyzeResponse(
        report=report,
        intent="standard_analysis",
        generation_mode="direct",
        estimated_cost_usd=0.0,
        workflow_steps=6,
    )


@app.get("/analyze", response_model=AnalyzeResponse)
async def analyze_get(user_id: str = "default", message: str = "", ticker: str = ""):
    req = AnalyzeRequest(user_id=user_id, message=message, ticker=ticker)
    return await analyze(req)


@app.get("/health", response_model=StatusResponse)
async def health():
    kb_entries = _kb.count_all() if _kb else 0
    user_count = 1
    if _portfolio_mgr:
        try:
            from .users.user_manager import UserManager
            user_count = len(UserManager().get_active_users())
        except Exception:
            user_count = 1
    return StatusResponse(status="ok", kb_entries=kb_entries, user_count=user_count)


PORTFOLIO_PARSE_PROMPT = """
从用户消息中提取持仓操作，输出严格JSON。
只输出JSON，不要其他文字。

支持的action:
- add_holding: 添加持仓（需要ticker, name, cost_price, quantity, entry_date）
- remove_holding: 移除持仓（需要ticker）
- add_watchlist: 加入自选（需要ticker, name）
- unknown: 无法解析

JSON格式:
{{
  "action": "...",
  "ticker": "6位数字代码",
  "name": "股票名称",
  "cost_price": 数字,
  "quantity": 整数,
  "entry_date": "YYYY-MM-DD"
}}

消息: {message}
"""


@app.post("/portfolio/chat", response_model=PortfolioChatResponse)
async def portfolio_chat(req: PortfolioChatRequest):
    """Parse natural language portfolio command and execute it."""
    if not req.message.strip():
        return PortfolioChatResponse(error="请输入持仓信息，例如：我买了600519茅台1000股成本1800")

    llm = _resolve_llm_for_portfolio()
    if not llm:
        return PortfolioChatResponse(error="LLM 不可用，请配置 API Key 后重试")

    try:
        prompt = PORTFOLIO_PARSE_PROMPT.format(message=req.message)
        resp = llm.invoke(prompt)
        content = resp.content if hasattr(resp, 'content') else str(resp)
        parsed = json.loads(content)

        action = parsed.get("action", "unknown")
        ticker = parsed.get("ticker", "")
        name = parsed.get("name", "")
        cost_price = float(parsed.get("cost_price", 0))
        quantity = int(parsed.get("quantity", 0))
        entry_date = parsed.get("entry_date", "")

        pm = _resolve_portfolio_mgr()

        if action == "add_holding" and ticker:
            pm.add_holding(ticker, name or ticker, cost_price, quantity, entry_date, req.user_id)
            return PortfolioChatResponse(
                action="add_holding", ticker=ticker, name=name,
                cost_price=cost_price, quantity=quantity,
                confirmation=f"已添加持仓：{ticker} {name}，成本{cost_price}元，{quantity}股"
            )
        elif action == "remove_holding" and ticker:
            pm.remove_holding(ticker, req.user_id)
            return PortfolioChatResponse(
                action="remove_holding", ticker=ticker,
                confirmation=f"已移除持仓：{ticker}"
            )
        elif action == "add_watchlist" and ticker:
            pm.add_to_watchlist(ticker, name or ticker, "", req.user_id)
            return PortfolioChatResponse(
                action="add_watchlist", ticker=ticker, name=name,
                confirmation=f"已加入自选：{ticker} {name}"
            )
        else:
            return PortfolioChatResponse(error="无法解析持仓信息。请提供股票代码和成本价")
    except Exception as e:
        logger.warning("Portfolio chat LLM parse failed: %s", e)
        return PortfolioChatResponse(error="无法解析持仓信息。请提供股票代码和成本价")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_graph() -> "TradingAgentsGraph":
    if _graph is None:
        raise HTTPException(
            status_code=503,
            detail="Graph not configured. Call api_server.configure() at startup.",
        )
    return _graph


def _resolve_llm_for_portfolio():
    """Create a minimal LLM client for portfolio parsing (offline from the graph)."""
    try:
        from .llm_clients import create_llm_client
        config = DEFAULT_CONFIG.copy()
        client = create_llm_client(
            provider=config.get("llm_provider", "deepseek"),
            model=config.get("quick_think_llm", "deepseek-v4-flash"),
        )
        return client.get_llm()
    except Exception as e:
        logger.warning("Cannot create LLM client for portfolio chat: %s", e)
        return None


def _resolve_portfolio_mgr():
    global _portfolio_mgr
    if _portfolio_mgr is None:
        from .portfolio.portfolio_manager import PortfolioManager
        _portfolio_mgr = PortfolioManager()
    return _portfolio_mgr
