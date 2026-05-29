from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
    get_degradation_instruction,
)
from tradingagents.dataflows.config import get_config


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            "You are a news and macroeconomics analyst. Your role is distinct from the social sentiment analyst: "
            "you focus on event-driven news, macroeconomic indicators, and official announcements.\n\n"
            "**Search Strategy:**\n"
            "1. Start with get_global_news(curr_date, look_back_days=7, limit=10) to establish macroeconomic context.\n"
             "2. Then use get_news(ticker='<stock_ticker>', start_date, end_date) "
             "for company-specific news. The ticker is the 6-digit A-share code (not the company name). "
             "Try the ticker directly; the data source will return all available news for that stock.\n\n"
            "**Source Credibility:**\n"
            "- Tier 1: Official announcements, regulatory filings, earnings reports (highest priority)\n"
            "- Tier 2: Authoritative financial media (Reuters, Bloomberg, Xinhua, etc.)\n"
            "- Tier 3: General news, industry blogs, analyst notes\n"
            "- When citing, note the source tier and prioritize Tier 1-2 sources.\n\n"
            "**Cross-Validation:**\n"
            "- If multiple sources contradict each other, flag the discrepancy explicitly.\n"
            "- When in doubt, defer to fundamental data over breaking news.\n\n"
            "**Degradation:**\n"
            "- If news searches return no results, clearly state 'No significant news found for this period.'\n"
            "- Offer a limited analysis based on global macro context alone.\n"
            "- Do NOT fabricate news events or speculate on unconfirmed reports.\n\n"
            "Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            " Make sure to append a Markdown table at the end of the report to organize key points."
            + get_language_instruction()
            + get_degradation_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "{system_message}\n\nFor your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        # DeepSeek requires strict tool_call→ToolMessage ordering,
        # but LangGraph's state mixes calls from multiple analyst cycles.
        # Analysts have all context via state fields, so clean history is safe.
        msgs = state["messages"]
        cleaned = [m for m in msgs if not isinstance(m, (AIMessage, ToolMessage)) or
                   (isinstance(m, AIMessage) and not m.tool_calls)]

        result = chain.invoke(cleaned)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
