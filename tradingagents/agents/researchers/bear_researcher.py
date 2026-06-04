from tradingagents.agents.utils.prompt_constants import get_anti_hallucination_instruction
from tradingagents.graph.context_manager import ContextWindowManager


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")

        # Round-awareness: first round vs rebuttal
        is_first_round = investment_debate_state.get("count", 0) == 0

        if is_first_round:
            round_instruction = (
                "**This is the opening round.** Present your comprehensive initial thesis "
                "based on the analyst reports. Do NOT reference opponent arguments "
                "(none exist yet as this is the first round)."
            )
            opponent_reference = "(No argument yet — this is the opening round. Present your initial thesis.)"
        else:
            round_instruction = (
                "**This is a rebuttal round.** Focus on countering the opponent's last argument "
                "with specific data and reasoning. Introduce at least ONE new piece of evidence "
                "not previously cited. Be conversational — speak as if you're in a live debate.\n"
                "If you find yourself agreeing with the opponent's key points, acknowledge "
                "the convergence honestly and suggest whether a decision can be reached."
            )
            opponent_reference = f"Last bull argument: {current_response}"

        # ---- ContextWindowManager: 三级策略管理上下文 (FIX-7) ----
        ctx = ContextWindowManager.inject_context(
            state, agent_type="bear", quick_llm=llm,
        )

        reports_text = ctx["reports_summary"]
        debate_history = ctx["debate_history"]
        market_context = ctx.get("market_context", state.get("market_context", ""))
        industry = ctx.get("industry", "")

        industry_info = ""
        if industry:
            industry_info = f"""
**⚠️ 行业锚定约束：** 你正在辩论的标的属于【{industry}】行业。所有论点必须基于该行业实际的商业模式、竞争格局和关键驱动因素。严禁使用与{industry}行业无关的术语或分析框架。
"""
            anti_patterns = ctx.get("anti_patterns", [])
            if anti_patterns:
                anti_str = "、".join(anti_patterns)
                industry_info += f"\n**⚠️ 严格禁止使用以下不适用于{industry}行业的术语：** {anti_str}"

        prompt = f"""{get_anti_hallucination_instruction("debate")}

{industry_info}You are a Risk Analyst evaluating the potential downsides of this investment. Your goal is to present a well-reasoned assessment emphasizing risk factors, challenges, and cautionary indicators. Leverage the provided research and data to highlight potential concerns and counter optimistic assumptions effectively.

{round_instruction}


**REQUIRED OUTPUT FORMAT** — You MUST include the following section in your response:

**本轮核心证据:**
[1-2 sentences stating the SINGLE strongest fact driving your position this round.
Cite a specific number or data point from the reports. No hedging, no "on one hand...".]
---

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {reports_text}
Conversation history of the debate:
{debate_history}
{opponent_reference}
Use this information to deliver a thorough risk assessment, engage in a dynamic debate, and demonstrate the potential challenges facing this investment.
"""

        if market_context:
            prompt += f"""
**Current Market Environment:**
{market_context}

Factor the above market environment into your risk assessment.
A strong bear thesis should identify how negative signals are
amplified by adverse market conditions, or acknowledge when
bearish signals contradict a bullish market backdrop.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        history = investment_debate_state.get("history", "")
        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "latest_speaker": "Bear",
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
