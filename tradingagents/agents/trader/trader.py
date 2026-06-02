"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.dataflows.a_share_constraints import format_limit_constraint

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction, get_degradation_instruction
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        company_display = state.get("company_name", "")
        industry = state.get("industry", "")
        instrument_context = build_instrument_context(company_name, industry=industry, company_name=company_display, quick_llm=llm)
        investment_plan = state["investment_plan"]
        market_type = state.get("market_type", "A_SHARE")
        limit_up = state.get("limit_up_price", 0.0)
        limit_down = state.get("limit_down_price", 0.0)
        cost_price = state.get("cost_price", 0.0)
        quantity = state.get("quantity", 0)

        # Build industry context note
        if industry:
            industry_note = f"\n\n**行业交易特征：** 当前标的属于 {industry} 行业。请考虑该行业典型的持仓周期、波动率特征和流动性特点。\n"
        else:
            industry_note = ""

        # Build position awareness note for the system message
        if cost_price > 0 and quantity > 0:
            position_note = (
                f"\n\n**Existing Position:** You currently hold {quantity} shares at "
                f"an average cost of {cost_price:.2f}. Factor this existing position into "
                f"your transaction proposal — consider whether to add, reduce, or hold."
            )
        else:
            position_note = ""

        # Build position context for the user message
        if cost_price > 0 and quantity > 0:
            position_context = (
                f"\n\n**Current Position:**\n"
                f"- Cost Price: {cost_price:.2f}\n"
                f"- Shares: {quantity}\n"
            )
        else:
            position_context = ""

        # Knowledge context injection: historical trading experience
        knowledge_context = state.get("knowledge_context", {})
        past_decisions = knowledge_context.get("past_decisions", "")
        confidence_tags = knowledge_context.get("_confidence_tags", {})
        history_section = ""
        if past_decisions:
            history_section = (
                "\n\n**Historical Trading Experience (from past decisions):**\n"
                f"{past_decisions}\n"
            )
            if confidence_tags:
                confidence_overall = confidence_tags.get("overall", "UNKNOWN")
                confidence_label = confidence_tags.get("label", "UNKNOWN")
                signal_dist = confidence_tags.get("signal_distribution", {})
                tag_summary_lines = [
                    f"- Overall Confidence: {confidence_overall} ({confidence_label})",
                    f"- Signals (last 30d): Buy={signal_dist.get('buy', 0)}, "
                    f"Sell={signal_dist.get('sell', 0)}, Hold={signal_dist.get('hold', 0)}",
                ]
                tag_summary = "\n".join(tag_summary_lines)
                history_section += f"\n**Confidence Analysis:**\n{tag_summary}\n"

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Trader — responsible for translating the Research Manager's directional "
                    "recommendation into a concrete transaction proposal (specific action, entry price, "
                    "stop-loss, and position size). The Research Manager decides the strategic direction; "
                    "you execute the tactical details.\n\n"
                    "**Signal Conflict Resolution:** When analyst reports give contradictory signals, "
                    "prioritize by: Fundamentals (long-term conviction) > Technical Analysis (medium-term) "
                    "> News/Sentiment (short-term noise). If conflict is severe, prefer Hold and explain why.\n\n"
                    "**Price Constraint Compliance:** The asset may have daily price limits. Ensure "
                    "entry_price and stop_loss fall within the allowed range. If limits prevent execution "
                    "at the desired level, flag this clearly.\n\n"
                    "Be decisive and ground every conclusion in specific analyst evidence."
                    + position_note
                    + get_language_instruction()
                    + get_degradation_instruction()
                    + industry_note
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                    f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                    f"insights from current technical market trends, macroeconomic indicators, and "
                    f"social media sentiment. Use this plan as a foundation for evaluating your next "
                    f"trading decision.\n\nProposed Investment Plan: {investment_plan}\n\n"
                    f"Leverage these insights to make an informed and strategic decision."
                    f"{position_context}"
                    f"{history_section}"
                    f"{format_limit_constraint(limit_up, limit_down, market_type)}"
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
