"""GraphExecutor — bridges the Planner output to DynamicGraphBuilder and invokes agents.

Orchestrates:
  Plan (from LLMPlanner) → DynamicGraphBuilder.build() → init_state → graph.invoke() → result
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from langgraph.prebuilt import ToolNode

from .dynamic_graph_builder import DynamicGraphBuilder
from ..agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState
from ..dataflows.a_stock_data import get_company_name
from ..industry.verifier import IndustryVerifier
from ..planner.schemas import Trigger, Context
from tradingagents.graph.report_renderer import ReportRenderer

logger = logging.getLogger(__name__)


class GraphExecutor:
    """Executes a workflow plan by building a dynamic LangGraph and invoking it."""

    def __init__(
        self,
        quick_thinking_llm,
        deep_thinking_llm,
        tool_nodes: Dict[str, ToolNode],
        max_debate_rounds: int = 2,
        max_risk_rounds: int = 2,
        max_recur_limit: int = 100,
        fan_out_enabled: bool = False,
        enable_checkpoint: bool = False,
        data_dir: str = "",
    ):
        self.quick_llm = quick_thinking_llm
        self.deep_llm = deep_thinking_llm
        self.tool_nodes = tool_nodes
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_rounds = max_risk_rounds
        self.max_recur_limit = max_recur_limit
        self.fan_out_enabled = fan_out_enabled
        self.enable_checkpoint = enable_checkpoint
        self.data_dir = data_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        plan: dict,
        trigger: Trigger,
        context: Context,
        callbacks: Optional[List] = None,
    ) -> dict:
        plan = _normalize_plan(plan)
        workflow = plan.get("workflow", [])
        if not workflow:
            return {
                "final_report": "",
                "raw_state": {},
                "intent": plan.get("intent", "unknown"),
                "error": "No workflow steps in plan",
            }

        init_state = self._build_init_state(plan, trigger, context)
        ticker = context.ticker or self._guess_ticker(trigger, plan)

        builder = DynamicGraphBuilder(
            self.quick_llm,
            self.deep_llm,
            self.tool_nodes,
            self.max_debate_rounds,
            self.max_risk_rounds,
            fan_out_enabled=self.fan_out_enabled,
        )

        # --- Checkpoint setup (crash recovery / resume) ---
        checkpointer_ctx = None
        checkpoint_thread_id = None
        checkpoint_task_id = None

        if self.enable_checkpoint and self.data_dir:
            from .checkpointer import (
                get_checkpointer_for_task,
                thread_id_for_task,
            )
            user_id = getattr(context, "user_id", "default") or "default"
            trigger_type = getattr(trigger, "type", "manual") or "manual"
            checkpoint_task_id = f"{ticker}:{user_id}:{trigger_type}"
            checkpoint_thread_id = thread_id_for_task(checkpoint_task_id)

            try:
                checkpointer_ctx = get_checkpointer_for_task(
                    self.data_dir, checkpoint_task_id
                )
                saver = checkpointer_ctx.__enter__()
                compiled = builder.build(plan, checkpointer=saver)
                logger.debug(
                    "Checkpoint enabled tid=%s task=%s",
                    checkpoint_thread_id, checkpoint_task_id,
                )
            except Exception as exc:
                logger.warning(
                    "Checkpoint setup failed, continuing without: %s", exc
                )
                compiled = builder.build(plan)
                checkpointer_ctx = None
                checkpoint_thread_id = None
        else:
            compiled = builder.build(plan)

        invoke_kwargs: dict = {
            "input": init_state,
            "config": {"recursion_limit": self.max_recur_limit},
        }
        if checkpoint_thread_id:
            invoke_kwargs["config"]["configurable"] = {
                "thread_id": checkpoint_thread_id
            }
        if callbacks:
            invoke_kwargs["config"]["callbacks"] = callbacks

        logger.info(
            "Executing plan: intent=%s mode=%s steps=%d",
            plan.get("intent", "?"),
            plan.get("_generation_mode", "?"),
            len(workflow),
        )

        graph_error: Exception | None = None
        try:
            final_state = compiled.invoke(**invoke_kwargs)
        except Exception as exc:
            logger.exception("Graph execution failed")
            graph_error = exc
            final_state = {}
        finally:
            if checkpointer_ctx is not None:
                try:
                    checkpointer_ctx.__exit__(None, None, None)
                except Exception:
                    pass

        if graph_error is not None:
            return {
                "final_report": "",
                "raw_state": {},
                "intent": plan.get("intent", "unknown"),
                "generation_mode": plan.get("_generation_mode", "unknown"),
                "template_id": plan.get("_template_id", ""),
                "estimated_cost_usd": plan.get("estimated_cost_usd", 0),
                "plan_workflow_steps": len(workflow),
                "error": "Graph execution failed — see logs",
            }

        if checkpoint_task_id and checkpoint_thread_id and self.data_dir:
            try:
                from .checkpointer import clear_checkpoint_for_task
                clear_checkpoint_for_task(
                    self.data_dir, checkpoint_task_id, checkpoint_thread_id
                )
                logger.debug("Checkpoint cleared for %s", checkpoint_task_id)
            except Exception:
                logger.debug("Failed to clear checkpoint", exc_info=True)

        report = self._extract_report(final_state)

        # Run IndustryVerifier on the assembled report (flag-and-continue)
        industry = final_state.get("industry", "")
        verification = None
        if industry and report:
            try:
                verification = IndustryVerifier.verify_industry_consistency(
                    industry=industry,
                    report=report,
                    quick_llm=self.quick_llm,
                )
                if not verification.get("consistent", True):
                    logger.warning(
                        "IndustryVerifier: consistency check failed for %s: %s",
                        final_state.get("company_of_interest", "unknown"),
                        verification.get("issues", []),
                    )
                    # Flag: append warning to the report
                    issues = "；".join(verification.get("issues", []))
                    report += (
                        f"\n\n⚠️ **行业一致性警告**"
                        f"（{verification.get('method', 'unknown')}）：{issues}"
                    )
            except Exception:
                logger.exception(
                    "IndustryVerifier: unexpected error during consistency check"
                )
                verification = {
                    "consistent": True,
                    "issues": ["verifier error"],
                    "severity": "warning",
                    "method": "error",
                }

        return {
            "final_report": report,
            "raw_state": final_state,
            "intent": plan.get("intent", ""),
            "generation_mode": plan.get("_generation_mode", ""),
            "template_id": plan.get("_template_id", ""),
            "estimated_cost_usd": plan.get("estimated_cost_usd", 0),
            "plan_workflow_steps": len(workflow),
            "industry_verification": verification,
        }

    # ------------------------------------------------------------------
    # Init state
    # ------------------------------------------------------------------

    def _build_init_state(self, plan: dict, trigger: Trigger, context: Context) -> dict:
        ticker = context.ticker or self._guess_ticker(trigger, plan)
        today = date.today().isoformat()

        # Look up company name for entity grounding (graceful fallback to ticker)
        try:
            company_name_str = get_company_name(ticker)
        except Exception:
            company_name_str = ticker

        debate_init = InvestDebateState(
            bull_history="",
            bear_history="",
            history="",
            current_response="",
            latest_speaker="",
            judge_decision="",
            count=0,
        )
        risk_init = RiskDebateState(
            aggressive_history="",
            conservative_history="",
            neutral_history="",
            history="",
            latest_speaker="",
            current_aggressive_response="",
            current_conservative_response="",
            current_neutral_response="",
            judge_decision="",
            count=0,
        )

        # Inject KB context into the initial message if available
        kb_hint = ""
        kb_results = plan.get("kb_results")
        if kb_results and hasattr(kb_results, "coverage_score") and kb_results.coverage_score > 0:
            kb_hint = f"\n[知识库覆盖率: {kb_results.coverage_score:.0%}]"
        if kb_results and hasattr(kb_results, "missing_aspects") and kb_results.missing_aspects:
            kb_hint += f"\n[需补充: {', '.join(kb_results.missing_aspects)}]"

        user_message = trigger.message or trigger.task or "analysis"
        if company_name_str != ticker:
            user_message = f"{user_message}（公司：{company_name_str}，代码：{ticker}）"
        user_message += kb_hint

        return {
            "messages": [("human", user_message)],
            "company_of_interest": ticker,
            "trade_date": today,
            "sender": "",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "market_context": context.market_state or "",
            "industry": context.industry or "",
            "company_name": company_name_str,
            "investment_debate_state": debate_init,
            "investment_plan": "",
            "trader_investment_plan": "",
            "risk_debate_state": risk_init,
            "final_trade_decision": "",
            "past_context": "",
            "knowledge_context": self._build_knowledge_context(plan),
            "market_type": "A_SHARE",
            "benchmark_ticker": "000300",
            "position_opened_date": "",
            "limit_up_price": 0.0,
            "limit_down_price": 0.0,
            "cost_price": 0.0,
            "quantity": 0,
            "position_pnl": 0.0,
            "position_pnl_pct": None,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_report(final_state: dict) -> str:
        """Build a complete analysis report from all graph state fields.

        Delegates to ReportRenderer.render() for consistent three-section format
        (核心结论 → 关键数据 → 风险提示) across all analyst sections.
        """
        return ReportRenderer.render(final_state, plan=None)

    @staticmethod

    def _build_knowledge_context(plan: dict) -> dict:
        """Build knowledge_context dict for agent consumption."""
        ctx: Dict[str, Any] = {}
        kb_results = plan.get("kb_results")
        if kb_results:
            if hasattr(kb_results, "results"):
                ctx["kb_results"] = kb_results.results
            if hasattr(kb_results, "coverage_score"):
                ctx["kb_coverage"] = kb_results.coverage_score
            if hasattr(kb_results, "missing_aspects"):
                ctx["kb_missing"] = kb_results.missing_aspects
        ctx["plan_intent"] = plan.get("intent", "")
        ctx["generation_mode"] = plan.get("_generation_mode", "")
        ctx["template_id"] = plan.get("_template_id", "")
        return ctx

    @staticmethod
    def _guess_ticker(trigger: Trigger, plan: dict) -> str:
        """Attempt to guess the ticker from message or plan.

        This is a best-effort heuristic; the Planner or caller should
        ideally set context.ticker before execution.
        """
        if trigger.message:
            # Very basic: look for 6-digit numbers
            import re
            digits = re.findall(r"\b\d{6}\b", trigger.message)
            if digits:
                return digits[0]
        return "unknown"


def _normalize_plan(plan: dict) -> dict:
    workflow = plan.get("workflow", [])
    if not workflow:
        return plan
    normalized = []
    for step in workflow:
        if isinstance(step, dict):
            normalized.append(step)
        elif hasattr(step, "step"):
            normalized.append({
                "step": step.step,
                "agent": step.agent,
                "task": step.task,
                "depends_on": step.depends_on or [],
                "expected_output": getattr(step, "expected_output", ""),
            })
        else:
            logger.warning("Unknown workflow step type: %s", type(step))
    return {**plan, "workflow": normalized}
