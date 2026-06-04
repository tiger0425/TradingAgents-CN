"""RED-phase TDD tests for analyst Pydantic schemas.

Tests that will fail (RED):
  1. ``test_market_analyst_uses_structured_output`` — ``market_analyst.py``
     does not yet call ``bind_structured(MarketReport, …)``.

Tests that should pass (GREEN):
  1. ``test_market_schema_exists`` — ``MarketReport`` already exists in ``schemas.py``.
  4. ``test_schema_validation`` — ``MarketReport`` accepts valid input.

Guardrail (must stay GREEN):
  3. ``test_debate_agents_no_structured_output`` — all 5 debate / risk
     agents must use free-text generation only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tradingagents.agents.schemas import MarketReport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AGENTS_DIR = (
    Path(__file__).resolve().parent.parent / "tradingagents" / "agents"
)

# 5 debate / risk agents that MUST use free-text generation only.
_DEBATE_AGENTS = (
    _AGENTS_DIR / "researchers" / "bull_researcher.py",
    _AGENTS_DIR / "researchers" / "bear_researcher.py",
    _AGENTS_DIR / "risk_mgmt" / "aggressive_debator.py",
    _AGENTS_DIR / "risk_mgmt" / "conservative_debator.py",
    _AGENTS_DIR / "risk_mgmt" / "neutral_debator.py",
)


def _source_contains(path: Path, *patterns: str) -> bool:
    """Return ``True`` if *any* of *patterns* appears in the file."""
    text = path.read_text(encoding="utf-8")
    return any(p in text for p in patterns)


# ---------------------------------------------------------------------------
# Test 1 — MarketReport schema existence (GREEN, schema already exists)
# ---------------------------------------------------------------------------


class TestMarketReportSchema:
    """``MarketReport`` exists in ``schemas.py``."""

    def test_market_schema_exists(self):
        """``MarketReport`` is importable from ``tradingagents.agents.schemas``."""
        assert MarketReport is not None
        assert issubclass(MarketReport, object)  # it's a valid symbol


# ---------------------------------------------------------------------------
# Test 2 — market_analyst must bind MarketReport (RED, not yet implemented)
# ---------------------------------------------------------------------------


class TestMarketAnalystStructuredOutput:
    """RED: ``market_analyst.py`` must call ``bind_structured(MarketReport, …)``."""

    def test_market_analyst_uses_structured_output(self):
        """The market analyst factory uses ``bind_structured(MarketReport, …)``."""
        src = (_AGENTS_DIR / "analysts" / "market_analyst.py").read_text(
            encoding="utf-8"
        )
        has_bind = "bind_structured" in src
        has_schema = "MarketReport" in src
        assert has_bind and has_schema, (
            "market_analyst.py must import and use bind_structured(MarketReport, …); "
            f"found 'bind_structured'={has_bind}, 'MarketReport'={has_schema}. "
            "See tradingagents/agents/utils/structured.py for the helper."
        )


# ---------------------------------------------------------------------------
# Test 3 — Guardrail: debate / risk agents must NOT use structured output
# ---------------------------------------------------------------------------


class TestDebateAgentsGuardrail:
    """Guardrail: debate / risk agents must NEVER use structured output.

    These agents argue / critique in free text only.  Introducing
    ``bind_structured`` or ``with_structured_output`` would constrain their
    responses and break the debate flow.
    """

    @pytest.mark.parametrize(
        "agent_path",
        [pytest.param(p, id=p.stem) for p in _DEBATE_AGENTS],
    )
    def test_debate_agents_no_structured_output(self, agent_path: Path):
        """Agent ``{agent_path.stem}`` does not use structured output."""
        assert not _source_contains(
            agent_path,
            "bind_structured",
            "with_structured_output",
        ), (
            f"{agent_path.name} uses structured output — "
            "debate agents must use free-text generation only"
        )


# ---------------------------------------------------------------------------
# Test 4 — MarketReport validation (GREEN, schema already validates)
# ---------------------------------------------------------------------------


class TestMarketReportValidation:
    """``MarketReport`` accepts and validates input correctly."""

    def test_schema_validation(self):
        """``MarketReport`` accepts valid minimal input."""
        report = MarketReport(
            ticker="000300",
            analysis_date="2025-06-03",
            trend="bullish",
            indicators_used=["RSI", "MACD"],
            key_findings=["Uptrend confirmed", "Volume expansion"],
            markdown_body="# Technical Analysis\n\nPrice is trending upward with strong volume.",
        )
        assert report.ticker == "000300"
        assert report.trend == "bullish"
        assert report.indicators_used == ["RSI", "MACD"]
        assert len(report.key_findings) == 2
