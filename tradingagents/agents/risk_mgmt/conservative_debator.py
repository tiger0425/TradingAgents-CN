

def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        # Truncate history to last ~20 lines (≈2 rounds) for context window protection
        history_lines = history.strip().split('\n')
        if len(history_lines) > 20:
            history = '\n'.join(history_lines[-20:])
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

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
            neut_ref = "(no neutral argument yet)"
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
            neut_ref = f"Neutral analyst said: {current_neutral_response}" if current_neutral_response.strip() else "(no neutral argument)"

        # ---- Industry anchoring ----
        industry = state.get("industry", "")
        industry_block = ""
        if industry:
            industry_block = f"""\n\n**⚠️ 行业锚定约束：** 你正在评估的交易标的属于【{industry}】行业。评估风险时必须基于该行业实际的商业模式、竞争格局和关键驱动因素。"""
            try:
                from tradingagents.industry.frameworks import IndustryFramework
                fw = IndustryFramework().lookup(industry)
                if fw and fw.get("anti_patterns"):
                    anti_str = "、".join(fw.get("anti_patterns", []))
                    industry_block += f"\n**严格禁止使用以下不适用于{industry}行业的术语：** {anti_str}"
            except Exception:
                pass

        prompt = f"""As the Conservative Risk Analyst, your primary objective is to protect assets, minimize volatility, and ensure steady, reliable growth. {round_instruction} You prioritize stability, security, and risk mitigation, carefully assessing potential losses, economic downturns, and market volatility. When evaluating the trader's decision or plan, critically examine high-risk elements, pointing out where the decision may expose the firm to undue risk and where more cautious alternatives could secure long-term gains. Here is the trader's decision:

{trader_decision}

Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a low-risk approach adjustment to the trader's decision:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} {agg_ref}. {neut_ref}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage by questioning their optimism and emphasizing the potential downsides they may have overlooked. Address each of their counterpoints to showcase why a conservative stance is ultimately the safest path for the firm's assets. Focus on debating and critiquing their arguments to demonstrate the strength of a low-risk strategy over their approaches. Output conversationally as if you are speaking without any special formatting.{industry_block}"""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
