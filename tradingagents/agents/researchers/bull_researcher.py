from tradingagents.graph.context_manager import ContextWindowManager


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        bull_history = investment_debate_state.get("bull_history", "")

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
            opponent_reference = f"Last bear argument: {current_response}"

        # ---- ContextWindowManager: 三级策略管理上下文 (FIX-7) ----
        ctx = ContextWindowManager.inject_context(
            state, agent_type="bull", quick_llm=llm,
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

        prompt = f"""{industry_info}You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

{round_instruction}


**REQUIRED OUTPUT FORMAT** — You MUST include the following section in your response:

**本轮核心证据:**
[1-2 sentences stating the SINGLE strongest fact driving your position this round.
Cite a specific number or data point from the reports. No hedging, no "on one hand...".]
---

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {reports_text}
Conversation history of the debate:
{debate_history}
{opponent_reference}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
"""
        if market_context:
            prompt += f"""
**Current Market Environment:**
{market_context}

Factor the above market environment into your analysis.
A strong bull thesis should acknowledge and explain why positive
signals persist despite any negative market backdrop, or why the
market tailwind amplifies bullish signals.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        history = investment_debate_state.get("history", "")
        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "latest_speaker": "Bull",
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
