"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_degradation_instruction
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Research Manager")

    def research_manager_node(state) -> dict:
        company_name = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(state["company_of_interest"], industry=industry, company_name=company_name)
        history = state["investment_debate_state"].get("history", "")

        investment_debate_state = state["investment_debate_state"]

        knowledge_context = state.get("knowledge_context", {})
        past_history = knowledge_context.get("past_decisions", "")
        historical_section = ""
        if past_history:
            historical_section = (
                f"\n\n**Historical Context:**\n"
                f"{past_history}\n"
                f"\nUse this historical context to calibrate your recommendation — "
                f"past patterns that worked or failed should inform your stance."
            )

        prompt = f"""As the Research Manager and debate facilitator, your role is to critically evaluate this round of debate and deliver a clear, actionable investment plan for the trader.

{instrument_context}{historical_section}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.

---

**Evidence Anchoring Rule:**
Both the Bull and Bear analysts were instructed to state a **本轮核心证据** — their single strongest fact this round. Your job:
1. Identify and extract each side's core evidence from their response.
2. Compare them directly: which evidence is more verifiable, more recent, more directly tied to price direction?
3. Your recommendation MUST cite which side's core evidence you found more convincing and WHY. If you cannot decide, explain what additional data would break the tie.


**Debate History:**
{history}

{get_language_instruction()}
{get_degradation_instruction()}"""

        if industry:
            prompt += f"\n\n**行业对标框架：** 相关标的属于 {industry} 行业。综合研判时应以该行业的核心竞争要素和投资逻辑为分析框架。\n"

        investment_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_research_plan,
            "Research Manager",
        )

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "latest_speaker": "Manager",
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
        }

    return research_manager_node
