

def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        # Truncate history to last ~20 lines (≈2 rounds) for context window protection
        history_lines = history.strip().split('\n')
        if len(history_lines) > 20:
            history = '\n'.join(history_lines[-20:])
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
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
            cons_ref = "(no conservative argument yet)"
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
            cons_ref = f"Conservative analyst said: {current_conservative_response}" if current_conservative_response.strip() else "(no conservative argument)"
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

        prompt = f"""As the Aggressive Risk Analyst, your role is to actively champion high-reward, high-risk opportunities, emphasizing bold strategies and competitive advantages. {round_instruction} When evaluating the trader's decision or plan, focus intently on the potential upside, growth potential, and innovative benefits—even when these come with elevated risk. Use the provided market data and sentiment analysis to strengthen your arguments and challenge the opposing views. Specifically, respond directly to each point made by the conservative and neutral analysts, countering with data-driven rebuttals and persuasive reasoning. Highlight where their caution might miss critical opportunities or where their assumptions may be overly conservative. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Company Fundamentals Report: {fundamentals_report}
Here is the current conversation history: {history} {cons_ref}. {neut_ref}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing any specific concerns raised, refuting the weaknesses in their logic, and asserting the benefits of risk-taking to outpace market norms. Maintain a focus on debating and persuading, not just presenting data. Challenge each counterpoint to underscore why a high-risk approach is optimal. Output conversationally as if you are speaking without any special formatting.{industry_block}"""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
