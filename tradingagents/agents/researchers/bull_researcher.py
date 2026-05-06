

def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

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
            opponent_reference = f"Last bear argument: {current_response}"

        # Keep only last 2 rounds of history to prevent context overflow
        history_lines = history.strip().split('\n')
        if len(history_lines) > 20:  # Roughly 2 rounds worth
            history = '\n'.join(history_lines[-20:])

        prompt = f"""You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

{round_instruction}

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
Company fundamentals report: {fundamentals_report}
Conversation history of the debate:
{history}
{opponent_reference}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
"""

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
