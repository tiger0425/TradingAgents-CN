"""Tests for CausalTracer — trace recording and extraction.

Covers:
  - Empty trace produces valid JSON with "Empty trace" summary
  - Analyst reports recorded correctly
  - Debate arguments extracted with round numbers
  - Judgment recording with winning side and basis
  - LLM extraction failures don't crash
  - build_trace_from_state integration with full final_state
  - to_dict() and save() produce valid JSON
"""
import json
import tempfile
from pathlib import Path

import pytest

from tradingagents.graph.causal_tracer import (
    CausalTracer,
    build_trace_from_state,
    _extract_rating,
    _extract_winning_side,
    _extract_basis,
)


# ── Mock LLM ────────────────────────────────────────────────────

class _MockLLM:
    """Mock LLM client that returns predictable content."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []

    def invoke(self, prompt: str):
        self.calls.append(prompt)
        if self.responses:
            return _FakeResponse(self.responses.pop(0))
        return _FakeResponse("[extraction failed]")


class _MockFailLLM:
    """Mock LLM that always raises."""

    def invoke(self, prompt: str):
        raise RuntimeError("simulated LLM failure")


class _FakeResponse:
    def __init__(self, content):
        self.content = content


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def tracer():
    return CausalTracer("TEST-001")


@pytest.fixture
def mock_llm():
    return _MockLLM(["RSI=68, approaching overbought"])


@pytest.fixture
def full_state():
    """Simulated final_state from a complete graph run."""
    return {
        "company_of_interest": "600519",
        "trade_date": "2026-05-28",
        "market_report": (
            "Market Analysis Report for 600519.\n"
            "**Key Finding**: RSI showing bullish divergence at 42.\n"
            "Volume increasing 15% above 20-day average."
        ),
        "sentiment_report": (
            "Social sentiment: 72% positive mentions.\n"
            "Retail investors showing strong interest in baijiu sector."
        ),
        "news_report": (
            "News: Q1 earnings beat estimates by 8%.\n"
            "Sector rotation into consumer staples observed."
        ),
        "fundamentals_report": (
            "Fundamentals: ROE 32%, PE 28, revenue growth 15% YoY.\n"
            "Debt-to-equity ratio improving to 0.3."
        ),
        "trader_investment_plan": (
            "Trader plan: Buy 100 shares at market open, "
            "stop loss at 5% below entry."
        ),
        "investment_debate_state": {
            "history": (
                "Bull Analyst: 本轮核心证据: Q1 revenue grew 18%, "
                "beating consensus by 5%. Strong channel expansion.\n"
                "Bear Analyst: 本轮核心证据: PE of 35 is 60% above "
                "industry average of 22. Regulatory headwinds increasing."
            ),
            "bull_history": "Bull Analyst: ...\n",
            "bear_history": "Bear Analyst: ...\n",
            "current_response": "",
            "judge_decision": (
                "Rating: Hold\n\n"
                "After reviewing both sides, I recommend Hold.\n"
                "The bull's growth thesis is strong but the bear's valuation "
                "concern is well-supported by industry data.\n"
                "Basis: bear's valuation evidence is more verifiable."
            ),
            "count": 2,
        },
        "risk_debate_state": {
            "history": (
                "Aggressive Analyst: 本轮核心证据: Risk-reward ratio at 3:1, "
                "strong upside potential.\n"
                "Conservative Analyst: 本轮核心证据: Max drawdown over 20% "
                "in last correction, position sizing critical.\n"
                "Neutral Analyst: 本轮核心证据: Balanced view — enter at "
                "support level with tight stop."
            ),
            "aggressive_history": "Aggressive Analyst: ...\n",
            "conservative_history": "Conservative Analyst: ...\n",
            "neutral_history": "Neutral Analyst: ...\n",
            "latest_speaker": "Neutral Analyst",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": (
                "**Rating**: Hold\n\n"
                "Given the risk assessment, I recommend Hold.\n"
                "The neutral analyst's balanced approach is convincing.\n"
                "Conservative concerns about drawdown are valid."
            ),
            "count": 3,
        },
        "final_trade_decision": ("**Rating**: Hold\nRecommend maintaining current position."),
        "investment_plan": "Research Manager plan: Hold based on balanced debate.",
        "market_context": "",
        "benchmark_ticker": "000300",
        "market_type": "A_SHARE",
    }


# ── Unit tests ──────────────────────────────────────────────────


@pytest.mark.unit
class TestCausalTracerBasics:
    """Basic tracer behavior."""

    def test_empty_trace_to_dict(self, tracer):
        result = tracer.to_dict()
        assert result["trace_id"] == "TEST-001"
        assert result["final_decision"] == "unknown"
        assert result["chain"] == []
        assert result["summary"] == "Empty trace"

    def test_empty_trace_save(self, tracer):
        with tempfile.TemporaryDirectory() as tmp:
            path = tracer.save(Path(tmp), "empty_trace")
            saved = json.loads(Path(path).read_text())
            assert saved["summary"] == "Empty trace"

    def test_chain_appends_in_order(self, tracer):
        tracer.record_judgment("Test Agent", "Hold", "Bull", ["Basis 1"])
        tracer.record_judgment("Test Agent 2", "Buy", "Bear", ["Basis 2"])
        assert len(tracer.chain) == 2
        assert tracer.chain[0]["agent"] == "Test Agent"
        assert tracer.chain[1]["agent"] == "Test Agent 2"


@pytest.mark.unit
class TestRecordAnalystReport:
    """record_analyst_report tests with and without LLM."""

    def test_without_llm_fallback(self, tracer):
        tracer.record_analyst_report("Market Analyst", "RSI shows bullish divergence at 42.")
        assert len(tracer.chain) == 1
        entry = tracer.chain[0]
        assert entry["agent"] == "Market Analyst"
        assert entry["output_type"] == "report"
        assert "RSI" in entry["key_claim"] or "bullish" in entry["key_claim"]

    def test_with_llm_extraction(self, tracer, mock_llm):
        tracer.record_analyst_report(
            "Market Analyst",
            "Long analysis report here... RSI=68, approaching overbought.",
            mock_llm,
        )
        entry = tracer.chain[0]
        assert "RSI" in entry["key_claim"]

    def test_llm_failure_does_not_crash(self, tracer):
        fail_llm = _MockFailLLM()
        tracer.record_analyst_report(
            "Market Analyst",
            "Test report content.",
            fail_llm,
        )
        assert len(tracer.chain) == 1
        assert tracer.chain[0]["key_claim"] == "[extraction failed]"

    def test_empty_report(self, tracer):
        tracer.record_analyst_report("Fundamentals Analyst", "")
        assert "empty" in tracer.chain[0]["key_claim"].lower()


@pytest.mark.unit
class TestRecordDebateArgument:
    """record_debate_argument tests."""

    def test_bull_argument(self, tracer):
        tracer.record_debate_argument(
            "Bull", "PE is low at 12, indicating undervaluation.", 1,
        )
        entry = tracer.chain[0]
        assert entry["agent"] == "Bull Researcher"
        assert entry["output_type"] == "argument"
        assert entry["round"] == 1
        assert "PE" in entry["claim"] or "undervalu" in entry["claim"].lower()

    def test_llm_failure_does_not_crash(self, tracer):
        fail_llm = _MockFailLLM()
        # Should not raise — falls back to heuristic extraction
        tracer.record_debate_argument(
            "Bear", "Valuation is stretched at 35x earnings.", 2, fail_llm,
        )
        entry = tracer.chain[0]
        # Heuristic fallback extracts claim from text
        assert entry["claim"] != ""
        assert "Valuation" in entry["claim"] or "35" in entry["claim"]

    def test_evidence_heuristic_extraction(self, tracer):
        tracer.record_debate_argument(
            "Bull", "PE ratio of 15.5 is attractive. Revenue growth 22%.", 1,
        )
        entry = tracer.chain[0]
        assert entry["evidence"] != ""


@pytest.mark.unit
class TestRecordJudgment:
    """record_judgment tests."""

    def test_judgment_records_all_fields(self, tracer):
        basis = ["Valuation concern supported", "Growth thesis lacks catalysts"]
        tracer.record_judgment("Research Manager", "Hold", "Bear", basis)
        entry = tracer.chain[0]
        assert entry["output_type"] == "judgment"
        assert entry["decision"] == "Hold"
        assert entry["winning_side"] == "Bear"
        assert len(entry["basis"]) == 2

    def test_multiple_judgments_extract_final(self, tracer):
        tracer.record_judgment("Research Manager", "Hold", "Bear", [])
        tracer.record_judgment("Portfolio Manager", "Buy", "Bull", [])
        result = tracer.to_dict()
        assert result["final_decision"] == "Buy"


@pytest.mark.unit
class TestRecordTraderPlan:
    """record_trader_plan tests."""

    def test_trader_plan_recorded(self, tracer):
        tracer.record_trader_plan("Buy 100 shares at $189, stop loss $179.")
        entry = tracer.chain[0]
        assert entry["agent"] == "Trader"
        assert entry["output_type"] == "report"

    def test_trader_plan_llm_failure(self, tracer):
        fail_llm = _MockFailLLM()
        tracer.record_trader_plan("Some plan text.", fail_llm)
        entry = tracer.chain[0]
        assert "extraction failed" in entry["key_claim"]


# ── Helper functions ─────────────────────────────────────────────


@pytest.mark.unit
class TestExtractRating:
    def test_buy(self):
        assert _extract_rating("Rating: Buy") == "Buy"

    def test_overweight_wins_over_hold(self):
        assert _extract_rating("Consider Overweight or Hold.") == "Overweight"

    def test_fallback_to_hold(self):
        assert _extract_rating("No clear direction.") == "Hold"

    def test_sell(self):
        assert _extract_rating("**Rating**: Sell") == "Sell"


@pytest.mark.unit
class TestExtractWinningSide:
    def test_bull_wins(self):
        assert _extract_winning_side("bullish thesis is stronger than bear concerns", "bull_bear") == "Bull"

    def test_bear_wins(self):
        assert _extract_winning_side("bear case is dominant, bearish signals prevail", "bull_bear") == "Bear"

    def test_balanced(self):
        assert _extract_winning_side("no clear advantage either way", "bull_bear") == "Balanced"

    def test_risk_aggressive(self):
        assert _extract_winning_side("aggressive stance justified by risk-reward", "risk") == "Aggressive"

    def test_risk_conservative(self):
        assert _extract_winning_side("conservative approach warranted", "risk") == "Conservative"

    def test_risk_balanced(self):
        assert _extract_winning_side("no opinion", "risk") == "Balanced"


@pytest.mark.unit
class TestExtractBasis:
    def test_extracts_list_items(self):
        text = "- Reason one for the decision\n- Reason two for the decision"
        basis = _extract_basis(text)
        assert len(basis) >= 1

    def test_extracts_sentences(self):
        text = "First key reason. Second important factor. Third consideration."
        basis = _extract_basis(text)
        assert len(basis) >= 2

    def test_empty_text(self):
        assert _extract_basis("") == []


# ── Integration tests ───────────────────────────────────────────


@pytest.mark.unit
class TestBuildTraceFromState:
    """Integration: build_trace_from_state with full final_state."""

    def test_full_chain_all_agents(self, tracer, full_state):
        build_trace_from_state(tracer, full_state)
        chain = tracer.chain

        agents_seen = {e["agent"] for e in chain}
        # Should cover: 4 analysts + 2 debate + RM + Trader + 3 risk + PM
        expected_agents = {
            "Market Analyst",
            "Social Media Analyst",
            "News Analyst",
            "Fundamentals Analyst",
            "Bull Researcher",
            "Bear Researcher",
            "Research Manager",
            "Trader",
            "Aggressive Researcher",
            "Conservative Researcher",
            "Neutral Researcher",
            "Portfolio Manager",
        }
        missing = expected_agents - agents_seen
        assert not missing, f"Missing agents in trace: {missing}"

        # Verify output types
        output_types = {e["output_type"] for e in chain}
        assert "report" in output_types
        assert "argument" in output_types
        assert "judgment" in output_types

    def test_empty_state_produces_empty_trace(self, tracer):
        build_trace_from_state(tracer, {})
        assert len(tracer.chain) == 0
        result = tracer.to_dict()
        assert result["summary"] == "Empty trace"

    def test_state_with_only_reports(self, tracer):
        state = {
            "market_report": "Market is bullish.",
            "fundamentals_report": "Strong fundamentals.",
        }
        build_trace_from_state(tracer, state)
        assert len(tracer.chain) == 2

    def test_state_with_debate_and_judgment(self, tracer):
        state = {
            "investment_debate_state": {
                "history": "Bull Analyst: Strong buy case.\nBear Analyst: Sell case.\n",
                "judge_decision": "Rating: Hold. Bull and bear are balanced.",
            },
        }
        build_trace_from_state(tracer, state)
        # Should have bull + bear + RM judgment = 3 entries
        assert len(tracer.chain) >= 3
        judgments = [e for e in tracer.chain if e["output_type"] == "judgment"]
        assert len(judgments) >= 1

    def test_llm_failure_during_build_does_not_crash(self, tracer, full_state):
        """Verify that LLM extraction failures don't crash the builder."""
        fail_llm = _MockFailLLM()
        # Should not raise
        build_trace_from_state(tracer, full_state, fail_llm)
        # Should still have entries (heuristic fallbacks)
        assert len(tracer.chain) > 0

    def test_summary_contains_key_agents(self, tracer, full_state):
        build_trace_from_state(tracer, full_state)
        result = tracer.to_dict()
        summary = result["summary"]
        assert "Research Manager" in summary
        assert "Portfolio Manager" in summary

    def test_save_produces_valid_json(self, tracer, full_state):
        build_trace_from_state(tracer, full_state)
        with tempfile.TemporaryDirectory() as tmp:
            path = tracer.save(Path(tmp), "test_trace")
            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert data["trace_id"] == "TEST-001"
            assert isinstance(data["chain"], list)
            assert isinstance(data["summary"], str)
            assert "generated_at" in data
