from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import json
import logging

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


class AnalyzeRequest(BaseModel):
    user_id: str = "default"
    message: str
    platform: str = "unknown"
    ticker: str = ""


class AnalyzeResponse(BaseModel):
    report: str
    intent: str
    generation_mode: str
    template_id: str
    estimated_cost_usd: float
    workflow_steps: int


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


# ---------------------------------------------------------------------------
# Dependency injection (set by configure() at startup)
# ---------------------------------------------------------------------------

_planner = None
_executor = None
_portfolio_mgr = None
_kb = None
_cost_tracker = None


def configure(planner, executor, portfolio_mgr=None, kb=None, cost_tracker=None):
    global _planner, _executor, _portfolio_mgr, _kb, _cost_tracker
    _planner = planner
    _executor = executor
    _portfolio_mgr = portfolio_mgr
    _kb = kb
    _cost_tracker = cost_tracker


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    executor = _resolve_executor()
    planner = _resolve_planner()

    from .planner.schemas import Trigger, Context

    trigger = Trigger(
        type="customer_message",
        message=req.message,
        task="",
        timeout_minutes=10,
    )

    portfolio_summary = ""
    if _portfolio_mgr:
        pf = _portfolio_mgr.load(req.user_id)
        holdings = pf.get("holdings", [])
        if holdings:
            portfolio_summary = ", ".join(
                f"{h.get('ticker', '?')}@{h.get('cost_price', 0)}x{h.get('quantity', 0)}"
                for h in holdings
            )

    context = Context(
        user_id=req.user_id,
        ticker=req.ticker,
        portfolio_summary=portfolio_summary,
    )

    plan = planner.plan(trigger, context)

    result = executor.execute(plan, trigger, context)

    if _cost_tracker and result.get("final_report"):
        _cost_tracker.record(
            req.user_id, "planner", "api", 0, 0,
            result.get("estimated_cost_usd", 0), "event",
        )

    return AnalyzeResponse(
        report=result.get("final_report", ""),
        intent=result.get("intent", "unknown"),
        generation_mode=result.get("generation_mode", "unknown"),
        template_id=result.get("template_id", ""),
        estimated_cost_usd=result.get("estimated_cost_usd", 0.0),
        workflow_steps=result.get("plan_workflow_steps", 0),
    )


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


@app.get("/analyze", response_model=AnalyzeResponse)
async def analyze_get(user_id: str = "default", message: str = "", ticker: str = ""):
    req = AnalyzeRequest(user_id=user_id, message=message, ticker=ticker)
    return await analyze(req)


@app.post("/portfolio/chat", response_model=PortfolioChatResponse)
async def portfolio_chat(req: PortfolioChatRequest):
    """Parse natural language portfolio command and execute it."""
    if not req.message.strip():
        return PortfolioChatResponse(error="请输入持仓信息，例如：我买了600519茅台1000股成本1800")

    planner = _resolve_planner()
    llm = planner.llm if hasattr(planner, 'llm') else None

    if llm:
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
                return PortfolioChatResponse(error="无法解析持仓信息。请提供股票代码和成本价，例如：我买了600519茅台1000股成本1800")
        except Exception as e:
            logger.warning("Portfolio chat LLM parse failed: %s", e)
            return PortfolioChatResponse(error="无法解析持仓信息。请提供股票代码和成本价，例如：我买了600519茅台1000股成本1800")

    return PortfolioChatResponse(error="LLM 不可用，请配置 API Key 后重试")


def _resolve_planner():
    if _planner is None:
        from .planner.llm_planner import LLMPlanner
        return LLMPlanner()
    return _planner


def _resolve_executor():
    if _executor is None:
        raise HTTPException(
            status_code=503,
            detail="Executor not configured. Call api_server.configure() at startup.",
        )
    return _executor


def _resolve_portfolio_mgr():
    global _portfolio_mgr
    if _portfolio_mgr is None:
        from .portfolio.portfolio_manager import PortfolioManager
        _portfolio_mgr = PortfolioManager()
    return _portfolio_mgr
