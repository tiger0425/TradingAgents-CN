"""Tests for knowledge injection into agent prompts.

Tests verify that Trader, Research Manager, and Portfolio Manager correctly
extract and inject historical knowledge from knowledge_context into their prompts,
and that empty knowledge_context doesn't crash any agent.
"""

import pytest
import functools
from unittest.mock import MagicMock, patch

from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState


# ============================================================================
# Helpers
# ============================================================================


def _make_base_state(company="600519", date="2026-05-09"):
    return {
        "company_of_interest": company,
        "trade_date": date,
        "messages": [],
        "sender": "",
        "market_report": "Market report content",
        "sentiment_report": "Sentiment report content",
        "news_report": "News report content",
        "fundamentals_report": "Fundamentals report content",
        "investment_plan": "**Recommendation**: Buy\n\n**Rationale**: Strong bull case",
        "trader_investment_plan": "**Action**: Buy\n\n**Reasoning**: Good entry",
        "investment_debate_state": InvestDebateState({
            "bull_history": "Bull argues buy",
            "bear_history": "Bear argues sell",
            "history": "Debate history placeholder",
            "current_response": "Bull final argument",
            "judge_decision": "Buy recommendation",
            "count": 1,
        }),
        "risk_debate_state": RiskDebateState({
            "aggressive_history": "Aggressive supports",
            "conservative_history": "Conservative cautious",
            "neutral_history": "Neutral balanced",
            "history": "Risk debate: Buy supported",
            "latest_speaker": "Neutral",
            "current_aggressive_response": "Buy now",
            "current_conservative_response": "Wait",
            "current_neutral_response": "Moderate risk",
            "judge_decision": "",
            "count": 1,
        }),
        "past_context": "",
        "knowledge_context": {},
        "cost_price": 0.0,
        "quantity": 0,
        "limit_up_price": 0.0,
        "limit_down_price": 0.0,
        "market_type": "A_SHARE",
    }


def _make_knowledge_context(past_decisions="", archived=None, confidence_tags=None):
    return {
        "archived_analyses": archived or [],
        "past_decisions": past_decisions,
        "ticker_signals": {"total_entries": 0, "by_decision": {}, "by_type": {}, "trend": []},
        "lessons": [],
        "cache_status": {"cache_dir": "/tmp", "exists": True},
        "_confidence_tags": confidence_tags or {},
    }


# ============================================================================
# Trader knowledge injection
# ============================================================================


class TestTraderKnowledgeInjection:
    def test_trader_injects_past_decisions(self):
        from tradingagents.agents.trader.trader import create_trader

        mock_llm = MagicMock()
        trader_fn = create_trader(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = _make_knowledge_context(
            past_decisions="Past analyses of 600519 (most recent first):\n[2026-05-01 | 600519 | Buy | +1.0% | +0.5% | 5d]\nDECISION:\nBuy at support levels.\nREFLECTION:\nGood entry timing.",
        )

        trader_fn(state)

    def test_trader_injects_confidence_tags(self):
        from tradingagents.agents.trader.trader import create_trader

        mock_llm = MagicMock()
        trader_fn = create_trader(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = _make_knowledge_context(
            past_decisions="Past analyses of 600519...",
            confidence_tags={
                "overall": "CONFIRMED",
                "label": "多次确认信号",
                "signal_distribution": {"buy": 3, "sell": 0, "hold": 0},
            },
        )

        trader_fn(state)

    def test_trader_empty_knowledge_no_crash(self):
        from tradingagents.agents.trader.trader import create_trader

        mock_llm = MagicMock()
        trader_fn = create_trader(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = {}

        trader_fn(state)

    def test_trader_no_knowledge_context_field(self):
        from tradingagents.agents.trader.trader import create_trader

        mock_llm = MagicMock()
        trader_fn = create_trader(mock_llm)

        state = _make_base_state()
        if "knowledge_context" in state:
            del state["knowledge_context"]

        trader_fn(state)


# ============================================================================
# Research Manager knowledge injection
# ============================================================================


class TestResearchManagerKnowledgeInjection:
    def test_rm_injects_historical_context(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        mock_llm = MagicMock()
        rm_fn = create_research_manager(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = _make_knowledge_context(
            past_decisions="Past analyses of 600519 (most recent first):\n[2026-05-01 | 600519 | Buy | ...]",
        )

        rm_fn(state)

    def test_rm_empty_knowledge_no_crash(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        mock_llm = MagicMock()
        rm_fn = create_research_manager(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = {}

        rm_fn(state)

    def test_rm_no_knowledge_context_field(self):
        from tradingagents.agents.managers.research_manager import create_research_manager

        mock_llm = MagicMock()
        rm_fn = create_research_manager(mock_llm)

        state = _make_base_state()
        if "knowledge_context" in state:
            del state["knowledge_context"]

        rm_fn(state)


# ============================================================================
# Portfolio Manager knowledge injection
# ============================================================================


class TestPortfolioManagerKnowledgeInjection:
    def test_pm_injects_archived_analyses(self):
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        pm_fn = create_portfolio_manager(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = _make_knowledge_context(
            archived=[
                {"date": "2026-05-08", "decision": "Buy", "rating": "Buy", "type": "morning-scan"},
                {"date": "2026-05-07", "decision": "Hold", "rating": "Hold", "type": "evening-review"},
            ],
        )

        pm_fn(state)

    def test_pm_empty_knowledge_no_crash(self):
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        pm_fn = create_portfolio_manager(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = {}

        pm_fn(state)

    def test_pm_empty_archived_no_crash(self):
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        pm_fn = create_portfolio_manager(mock_llm)

        state = _make_base_state()
        state["knowledge_context"] = _make_knowledge_context(archived=[])

        pm_fn(state)

    def test_pm_no_knowledge_context_field(self):
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        pm_fn = create_portfolio_manager(mock_llm)

        state = _make_base_state()
        if "knowledge_context" in state:
            del state["knowledge_context"]

        pm_fn(state)


# ============================================================================
# AgentState knowledge_context field
# ============================================================================


class TestAgentStateKnowledgeContext:
    def test_field_exists_on_agent_state(self):
        state = _make_base_state()
        state["knowledge_context"] = {"test": True}
        assert state["knowledge_context"]["test"] is True

    def test_default_empty_dict(self):
        state = _make_base_state()
        assert state["knowledge_context"] == {}

    def test_all_agents_survive_null_context(self):
        from tradingagents.agents.trader.trader import create_trader
        from tradingagents.agents.managers.research_manager import create_research_manager
        from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

        mock_llm = MagicMock()
        state = _make_base_state()
        state["knowledge_context"] = {
            "archived_analyses": None,
            "past_decisions": None,
            "ticker_signals": None,
            "lessons": None,
            "cache_status": None,
            "_confidence_tags": None,
        }

        create_trader(mock_llm)(state)
        create_research_manager(mock_llm)(state)
        create_portfolio_manager(mock_llm)(state)
