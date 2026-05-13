from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
