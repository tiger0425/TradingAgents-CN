"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.dataflows.a_share_constraints import format_limit_constraint

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]
        market_type = state.get("market_type", "A_SHARE")
        limit_up = state.get("limit_up_price", 0.0)
        limit_down = state.get("limit_down_price", 0.0)

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
                    + get_language_instruction()
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
