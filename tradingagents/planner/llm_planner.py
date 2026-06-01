import json
import logging
from copy import deepcopy

from .schemas import WorkflowPlan, WorkflowStep, Trigger, Context, KBContext, MatchResult
from .template_matcher import TemplateMatcher
from .template_evolver import TemplateEvolver

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """
你是华创量化研究院的所长。根据触发事件和用户上下文，生成 Agent 执行计划。

## 可用研究员
| ID | 角色 | 何时用 |
|----|------|--------|
| market_analyst | 技术面 | K线/均线/MACD/RSI，所有场景 |
| fundamentals_analyst | 基本面 | ROE/财报/估值，深度个股分析 |
| news_analyst | 新闻 | 公告/新闻，持仓预警 |
| social_analyst | 舆情 | 社交情绪(可选) |
| macro_analyst | 宏观 | 指数/汇率/北向，晨会/周选股 |
| bull_researcher | 多方 | 辩论(需配对bear) |
| bear_researcher | 空方 | 辩论(需配对bull) |
| research_manager | 研究主管 | 辩论汇总 |
| trader | 交易员 | 买卖方案/四方案模拟 |
| risk_aggressive/conservative/neutral | 风控 | 三方风控辩论 |
| portfolio_manager | 组合经理 | 最终决策/报告 |

## 规划原则
1. 定时任务不超过4个Agent，不包含辩论
2. 个股深度分析需要bull_researcher+bear_researcher辩论（两个必须同时出现，缺一不可）
3. 解套方案需要trader做四方案模拟
4. 风控辩论必须同时安排 risk_aggressive + risk_conservative + risk_neutral 三方（三个必须同时出现，缺一不可）
5. 如果不安排风控辩论，则不要单独出现任何一个 risk_* agent
6. research_manager 必须与 bull_researcher+bear_researcher 同时出现，辩论结束后调用

## 输出格式
严格JSON: {"intent":"...", "workflow":[{"step":1, "agent":"...", "task":"...", "depends_on":[], "expected_output":"..."}]}
"""


class LLMPlanner:
    def __init__(self, kb=None, llm=None, templates_dir="~/.tradingagents/templates"):
        self.kb = kb
        self.llm = llm
        self.template_matcher = TemplateMatcher(templates_dir)
        self.template_evolver = TemplateEvolver(templates_dir)

    def plan(self, trigger: Trigger, context: Context) -> dict:
        plan = self._plan_internal(trigger, context)
        workflow = plan.get("workflow", [])
        plan["workflow"] = [
            WorkflowStep(**s) if isinstance(s, dict) else s for s in workflow
        ]
        return plan

    def _plan_internal(self, trigger: Trigger, context: Context) -> dict:
        kb_ctx = KBContext()
        if self.kb:
            kb_ctx = self._query_kb(trigger, context)

        weighted_coverage = kb_ctx.coverage_detail.get("weighted_coverage", kb_ctx.coverage_score)
        stale_items = kb_ctx.coverage_detail.get("stale_items", [])

        if stale_items:
            logger.info("KB stale items: %s — will NOT skip analysis", stale_items)

        if weighted_coverage >= 0.7 and not stale_items:
            return self._plan_with_kb(kb_ctx, trigger, context)

        match = self.template_matcher.match(trigger, context)
        return self._plan_from_match(match, trigger, context)

    def _query_kb(self, trigger: Trigger, context: Context) -> KBContext:
        raw = self.kb.query_for_event(trigger, context)
        return KBContext(
            results=raw.get("results", []),
            coverage_score=raw.get("coverage_score", 0.0),
            coverage_detail=raw.get("coverage_detail", {}),
            missing_aspects=raw.get("missing_aspects", []),
        )

    def _plan_with_kb(self, kb_ctx: KBContext, trigger: Trigger, context: Context) -> dict:
        task = trigger.task or "analysis"
        return {
            "intent": task,
            "reasoning": f"KB coverage {kb_ctx.coverage_score:.0%}",
            "workflow": [{
                "step": 1, "agent": "portfolio_manager",
                "task": f"基于KB数据生成{task}报告",
                "depends_on": [], "expected_output": f"{task}报告"
            }],
            "final_output_type": "report",
            "urgency": "medium",
            "estimated_cost_usd": 0.10,
            "kb_results": kb_ctx,
            "_generation_mode": "template_exact",
        }

    def _plan_from_match(self, match: MatchResult, trigger: Trigger, context: Context) -> dict:
        if match.mode == "exact_match":
            plan = deepcopy(match.template)
            plan["workflow"] = self._substitute_vars(plan.get("workflow", []), context)
            plan["_generation_mode"] = "template_exact"
            plan["_template_id"] = match.template.get("template_id", "")
            return plan
        if match.mode == "fuzzy_match":
            plan = deepcopy(match.template)
            plan["workflow"] = self._substitute_vars(plan.get("workflow", []), context)
            plan["_generation_mode"] = "template_refined"
            plan["_template_id"] = match.template.get("template_id", "")
            return plan
        return self._generate_from_llm(trigger, context)

    def _generate_from_llm(self, trigger: Trigger, context: Context) -> dict:
        if not self.llm:
            return self._fallback_plan(trigger)
        try:
            prompt = f"{PLANNER_PROMPT}\n\n## 触发事件\n类型:{trigger.type} 任务:{trigger.task}\n消息:{trigger.message}\n\n## 上下文\n持仓:{context.portfolio_summary or '无'} 自选:{context.watchlist_summary or '无'} 标的:{context.ticker or '无'} 行业:{context.industry or '无'}\n\n请生成执行计划JSON。"
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, 'content') else ""
            plan = self._parse_json_response(content)
            plan["_generation_mode"] = "llm_full"
            return plan
        except Exception as e:
            logger.warning("LLM plan failed: %s", e)
            return self._fallback_plan(trigger)

    @staticmethod
    def _parse_json_response(content: str) -> dict:
        """Extract JSON from an LLM response, tolerating markdown code blocks."""
        # Direct parse
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            pass
        # Markdown code block: ```json ... ```
        import re
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
        # Find outermost { ... } or [ ... ]
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = content.find(start_char)
            end = content.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start:end + 1])
                except (json.JSONDecodeError, ValueError):
                    pass
        raise ValueError(f"Cannot parse JSON from response")

    def _fallback_plan(self, trigger: Trigger) -> dict:
        return {
            "intent": trigger.task or "analysis",
            "workflow": [{"step": 1, "agent": "portfolio_manager",
                          "task": f"执行{trigger.task}", "depends_on": [], "expected_output": "报告"}],
            "final_output_type": "report",
            "_generation_mode": "llm_fallback",
            "estimated_cost_usd": 0.05,
        }

    def _substitute_vars(self, workflow: list, context: Context) -> list:
        result = []
        for step in workflow:
            s = deepcopy(step)
            for key in ("task", "expected_output"):
                if key in s and isinstance(s[key], str):
                    s[key] = (s[key].replace("{ticker}", context.ticker or "?")
                               .replace("{industry}", context.industry or ""))
            result.append(s)
        return result
