"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their outputs follow consistent section headers across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- A render helper turns the parsed Pydantic instance back into the same
  markdown shape the rest of the system already consumes, so display,
  memory log, and saved reports keep working unchanged
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier rating used by the Research Manager and Portfolio Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round.  Position sizing and the nuanced
    Overweight / Underweight calls happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments. "
            "Chinese: 投资建议评级，从 Buy / Overweight / Hold / Underweight / Sell "
            "中选择一个。仅当多空双方证据确实平衡时才选择 Hold，否则选择论据更强的一方。"
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate. "
            "Chinese: 对多空双方辩论要点的对话式总结，结尾说明哪些论据最终促成了该建议。"
            "以自然的语气书写，如同与团队成员交流。"
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description=(
            "The transaction direction. Exactly one of Buy / Hold / Sell. "
            "Chinese: 交易方向，从 Buy / Hold / Sell 中选择一个。"
        ),
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences. "
            "Chinese: 基于分析师报告和研究计划阐述该交易操作的依据。2-4 句话。"
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown.

    The trailing ``FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**`` line is
    preserved for backward compatibility with the analyst stop-signal text
    and any external code that greps for it.
    """
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    parts.extend([
        "",
        f"FINAL TRANSACTION PROPOSAL: **{proposal.action.value.upper()}**",
    ])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured output produced by the Portfolio Manager.

    The model fills every field as part of its primary LLM call; no separate
    extraction pass is required. Field descriptions double as the model's
    output instructions, so the prompt body only needs to convey context and
    the rating-scale guidance.
    """

    rating: PortfolioRating = Field(
        description=(
            "The final position rating. Exactly one of Buy / Overweight / Hold / "
            "Underweight / Sell, picked based on the analysts' debate. "
            "Chinese: 最终持仓评级，从 Buy / Overweight / Hold / Underweight / Sell "
            "中选择一个，基于分析师辩论结果决定。"
        ),
    )
    executive_summary: str = Field(
        description=(
            "A concise action plan covering entry strategy, position sizing, "
            "key risk levels, and time horizon. Two to four sentences. "
            "Chinese: 简洁的行动计划，涵盖入场策略、仓位大小、关键风险水平和时间跨度。"
            "2-4 句话。"
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis. "
            "Chinese: 基于分析师辩论中具体证据的详细推理。如果提示上下文中引用了历史经验，"
            "请将其纳入分析；否则仅基于当前分析进行论述。"
        ),
    )
    price_target: Optional[float] = Field(
        default=None,
        description="Optional target price in the instrument's quote currency.",
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )


def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render a PortfolioDecision back to the markdown shape the rest of the system expects.

    Memory log, CLI display, and saved report files all read this markdown,
    so the rendered output preserves the exact section headers (``**Rating**``,
    ``**Executive Summary**``, ``**Investment Thesis**``) that downstream
    parsers and the report writers already handle.
    """
    parts = [
        f"**Rating**: {decision.rating.value}",
        "",
        f"**Executive Summary**: {decision.executive_summary}",
        "",
        f"**Investment Thesis**: {decision.investment_thesis}",
    ]
    if decision.price_target is not None:
        parts.extend(["", f"**Price Target**: {decision.price_target}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon**: {decision.time_horizon}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Market Analyst
# ---------------------------------------------------------------------------


class MarketReport(BaseModel):
    """Structured technical analysis report produced by the Market Analyst.

    Covers price action, volume, and indicator-based readings for a ticker.
    The trend direction and supporting indicators are captured in structured
    fields, while the full narrative lives in markdown_body.
    """

    ticker: str = Field(description="Ticker symbol being analysed.")
    analysis_date: str = Field(description="Date of the analysis in YYYY-MM-DD format.")
    trend: Literal["bullish", "bearish", "neutral"] = Field(
        description=(
            "Overall market / price trend direction. "
            "Chinese: 市场/价格趋势方向，可选 bullish / bearish / neutral。"
        ),
    )
    indicators_used: list[str] = Field(
        description="List of technical indicators consulted (e.g. RSI, MACD, SMA50, SMA200).",
    )
    key_findings: list[str] = Field(
        description="Key technical observations that drove the trend conclusion.",
    )
    markdown_body: str = Field(
        description="Full prose technical analysis in markdown format.",
    )


def render_market_report(report: MarketReport) -> str:
    """Render a MarketReport to markdown for storage and downstream agents."""
    indicators = ", ".join(report.indicators_used)
    findings = "\n".join(f"- {f}" for f in report.key_findings)
    return "\n".join([
        f"# Market Analysis: {report.ticker}",
        "",
        f"**Date**: {report.analysis_date}",
        f"**Trend**: {report.trend}",
        f"**Indicators Used**: {indicators}",
        "",
        "**Key Findings**:",
        findings,
        "",
        "---",
        "",
        report.markdown_body,
    ])


# ---------------------------------------------------------------------------
# Fundamentals Analyst
# ---------------------------------------------------------------------------


class FundamentalsReport(BaseModel):
    """Structured fundamentals analysis report produced by the Fundamentals Analyst.

    Captures financial health, key metrics, and narrative analysis for a
    ticker based on financial statements and valuation models.
    """

    ticker: str = Field(description="Ticker symbol being analysed.")
    analysis_date: str = Field(description="Date of the analysis in YYYY-MM-DD format.")
    financial_health: Literal["strong", "moderate", "weak"] = Field(
        description=(
            "Assessment of the company's financial health based on its "
            "financial statements. "
            "Chinese: 基于财务报表的公司财务健康评估，可选 strong / moderate / weak。"
        ),
    )
    key_metrics: dict[str, float] = Field(
        description="Key financial metrics (e.g. P/E ratio, EPS growth, debt-to-equity).",
    )
    key_findings: list[str] = Field(
        description="Key fundamental observations that drove the health assessment.",
    )
    markdown_body: str = Field(
        description="Full prose fundamentals analysis in markdown format.",
    )


def render_fundamentals_report(report: FundamentalsReport) -> str:
    """Render a FundamentalsReport to markdown for storage and downstream agents."""
    metrics = "\n".join(f"- **{k}**: {v}" for k, v in report.key_metrics.items())
    findings = "\n".join(f"- {f}" for f in report.key_findings)
    return "\n".join([
        f"# Fundamentals Analysis: {report.ticker}",
        "",
        f"**Date**: {report.analysis_date}",
        f"**Financial Health**: {report.financial_health}",
        "",
        "**Key Metrics**:",
        metrics,
        "",
        "**Key Findings**:",
        findings,
        "",
        "---",
        "",
        report.markdown_body,
    ])


# ---------------------------------------------------------------------------
# News Analyst
# ---------------------------------------------------------------------------


class NewsReport(BaseModel):
    """Structured news-analysis report produced by the News Analyst.

    Summarises recent news events relevant to the ticker and assigns an
    aggregate sentiment direction.
    """

    ticker: str = Field(description="Ticker symbol being analysed.")
    analysis_date: str = Field(description="Date of the analysis in YYYY-MM-DD format.")
    sentiment: Literal["positive", "negative", "neutral"] = Field(
        description=(
            "Aggregate news sentiment for the ticker. "
            "Chinese: 该标的的整体新闻情绪，可选 positive / negative / neutral。"
        ),
    )
    key_events: list[str] = Field(
        description="Key recent news events that influenced the sentiment assessment.",
    )
    markdown_body: str = Field(
        description="Full prose news analysis in markdown format.",
    )


def render_news_report(report: NewsReport) -> str:
    """Render a NewsReport to markdown for storage and downstream agents."""
    events = "\n".join(f"- {e}" for e in report.key_events)
    return "\n".join([
        f"# News Analysis: {report.ticker}",
        "",
        f"**Date**: {report.analysis_date}",
        f"**Sentiment**: {report.sentiment}",
        "",
        "**Key Events**:",
        events,
        "",
        "---",
        "",
        report.markdown_body,
    ])


# ---------------------------------------------------------------------------
# Social / Sentiment Analyst
# ---------------------------------------------------------------------------


class SocialReport(BaseModel):
    """Structured social-media / sentiment report produced by the Social Analyst.

    Captures aggregate social sentiment, trending topics, and narrative
    analysis from social media and alternative data sources.
    """

    ticker: str = Field(description="Ticker symbol being analysed.")
    analysis_date: str = Field(description="Date of the analysis in YYYY-MM-DD format.")
    sentiment: Literal["bullish", "bearish", "neutral"] = Field(
        description=(
            "Aggregate social-media sentiment for the ticker. "
            "Chinese: 该标的的社交媒体整体情绪，可选 bullish / bearish / neutral。"
        ),
    )
    hot_topics: list[str] = Field(
        description="Trending social-media topics relevant to the ticker.",
    )
    markdown_body: str = Field(
        description="Full prose social-media analysis in markdown format.",
    )


def render_social_report(report: SocialReport) -> str:
    """Render a SocialReport to markdown for storage and downstream agents."""
    topics = "\n".join(f"- {t}" for t in report.hot_topics)
    return "\n".join([
        f"# Social Media Analysis: {report.ticker}",
        "",
        f"**Date**: {report.analysis_date}",
        f"**Sentiment**: {report.sentiment}",
        "",
        "**Hot Topics**:",
        topics,
        "",
        "---",
        "",
        report.markdown_body,
    ])
