

def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

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

        # Keep only last 2 rounds of history to prevent context overflow
        history_lines = history.strip().split('\n')
        if len(history_lines) > 20:  # Roughly 2 rounds worth
            history = '\n'.join(history_lines[-20:])

        prompt = f"""You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

{round_instruction}

Key points to focus on:

- Risks and Challenges: Highlight factors like market saturation, financial instability, or macroeconomic threats that could hinder the stock's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining innovation, or threats from competitors.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate:
{history}
{opponent_reference}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock.
"""

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
