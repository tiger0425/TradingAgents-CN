

def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        # Truncate history to last ~20 lines (≈2 rounds) for context window protection
        history_lines = history.strip().split('\n')
        if len(history_lines) > 20:
            history = '\n'.join(history_lines[-20:])
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        trader_decision = state["trader_investment_plan"]

        count = risk_debate_state["count"]
        is_first_round = count == 0

        if is_first_round:
            round_instruction = (
                "This is the OPENING ROUND. Present your initial risk assessment "
                "independently — no arguments from other analysts exist yet. "
                "Do NOT reference or respond to other viewpoints."
            )
            agg_ref = "(no aggressive argument yet)"
            cons_ref = "(no conservative argument yet)"
        else:
            round_instruction = (
                "This is a REBUTTAL ROUND. Focus on countering the specific points "
                "raised by the other analysts. Introduce risk metrics or considerations "
                "the opponent overlooked.\n"
                "At least ONE new risk metric, data point, or analytical angle must be introduced "
                "this round.\n"
                "If you find common ground with the other analysts on key risk dimensions, "
                "acknowledge it rather than fabricating disagreement."
            )
            agg_ref = f"Aggressive analyst said: {current_aggressive_response}" if current_aggressive_response.strip() else "(no aggressive argument)"
            cons_ref = f"Conservative analyst said: {current_conservative_response}" if current_conservative_response.strip() else "(no conservative argument)"

        prompt = f"""As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing both the potential benefits and risks of the trader's decision or plan. {round_instruction} You prioritize a well-rounded approach, evaluating the upsides and downsides while factoring in broader market trends, potential economic shifts, and diversification strategies.Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} {agg_ref}. {cons_ref}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by analyzing both sides critically, addressing weaknesses in the aggressive and conservative arguments to advocate for a more balanced approach. Challenge each of their points to illustrate why a moderate risk strategy might offer the best of both worlds, providing growth potential while safeguarding against extreme volatility. Focus on debating rather than simply presenting data, aiming to show that a balanced view can lead to the most reliable outcomes. Output conversationally as if you are speaking without any special formatting."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
