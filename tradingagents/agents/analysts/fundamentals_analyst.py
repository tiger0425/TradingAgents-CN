from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_language_instruction,
    get_degradation_instruction,
)
from tradingagents.dataflows.config import get_config


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_fundamentals,
            get_balance_sheet,
            get_cashflow,
            get_income_statement,
            get_insider_transactions,
        ]

        system_message = (
            "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
            + " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements."
            + get_language_instruction()
            + get_degradation_instruction()
            + " Remember: you are the fundamentals specialist. Your analysis feeds into the broader investment thesis but you are NOT responsible for the final trading decision.",
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

        # DeepSeek 兼容：清理孤立 tool_calls，防止 400 错误
        msgs = state["messages"]
        cleaned = []
        pending_tool_ids = set()
        for m in msgs:
            if hasattr(m, "tool_calls") and m.tool_calls:
                tc_ids = {tc.get("id", "") for tc in m.tool_calls if hasattr(tc, "get")}
                pending_tool_ids |= tc_ids
                cleaned.append(m)
            elif hasattr(m, "name") and m.name == "tool" and hasattr(m, "tool_call_id"):
                if m.tool_call_id in pending_tool_ids:
                    pending_tool_ids.discard(m.tool_call_id)
                    cleaned.append(m)
            else:
                cleaned.append(m)

        result = chain.invoke(cleaned)

        report = result.content if result.content else ""

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
